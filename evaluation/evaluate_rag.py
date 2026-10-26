"""Evaluate ChemLib-AI's real RAG pipeline with RAGAS.

    python -m evaluation.evaluate_rag --dataset evaluation/datasets/<your>.json

What it does
------------
1. Loads a question set (JSON or CSV, see evaluation/README.md) and validates it.
2. Runs every question through the *application's own* ``RAGService`` over the application's
   own vector store, routed exactly like the chat page (a ``document`` scope, or the
   "compare A and B" detection from ``app/compare_intent.py``). The store is wrapped by a
   recorder, so the contexts RAGAS judges are the chunks the LLM actually received.
3. Scores answers with RAGAS 0.4 (``ragas.metrics.collections`` + ``ascore``; the deprecated
   ``evaluate()`` / ``ragas.metrics`` imports are not used).
4. Writes <run>.csv, <run>.json and <run>.md to ``result/``.

Needs an LLM judge (and, for answer relevancy / correctness, embeddings) in addition to the
application's own LLM; see "Dependencies and cost" in evaluation/README.md. Nothing is
fabricated: a question that failed is recorded as failed, never scored.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("evaluation")

DEFAULT_RESULT_DIR = ROOT / "result"
DEFAULT_JUDGE_MAX_TOKENS = 4096
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# Metrics: which RAGAS metric needs which inputs. Only these are ever requested.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricSpec:
    cls: str                       # class name in ragas.metrics.collections
    inputs: tuple[str, ...]        # keyword arguments of its ``ascore``
    needs_embeddings: bool = False

    @property
    def needs_reference(self) -> bool:
        return "reference" in self.inputs


METRICS: dict[str, MetricSpec] = {
    "faithfulness": MetricSpec("Faithfulness", ("user_input", "response", "retrieved_contexts")),
    "answer_relevancy": MetricSpec("AnswerRelevancy", ("user_input", "response"), needs_embeddings=True),
    "context_precision": MetricSpec("ContextPrecision", ("user_input", "reference", "retrieved_contexts")),
    "context_recall": MetricSpec("ContextRecall", ("user_input", "retrieved_contexts", "reference")),
    "answer_correctness": MetricSpec(
        "AnswerCorrectness", ("user_input", "response", "reference"), needs_embeddings=True
    ),
}
DEFAULT_METRICS = list(METRICS)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class EvalItem:
    id: str
    question: str
    reference: str | None = None   # ground truth answer
    document: str | None = None    # optional scope: a file name (or document id) in the library
    type: str = ""                 # free label for per-type results: direct / multi_step / comparison ...


@dataclass
class DatasetLoad:
    items: list[EvalItem] = field(default_factory=list)
    invalid: list[dict] = field(default_factory=list)   # {"row": n, "reason": str}


_REFERENCE_KEYS = ("ground_truth", "reference", "answer")


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_dataset(path: str | Path) -> DatasetLoad:
    """Read a JSON (list, or {"questions": [...]}) or CSV dataset. Bad rows are reported, not fatal."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError('A JSON dataset must be a list of objects, or {"questions": [...]}.')
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        raise ValueError(f"Unsupported dataset format '{suffix}' (use .json or .csv).")

    load = DatasetLoad()
    seen: set[str] = set()
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            load.invalid.append({"row": number, "reason": "row is not an object"})
            continue
        question = _clean(row.get("question"))
        if not question:
            load.invalid.append({"row": number, "reason": "missing 'question'"})
            continue
        item_id = _clean(row.get("id")) or f"q{number:03d}"
        if item_id in seen:
            load.invalid.append({"row": number, "reason": f"duplicate id '{item_id}'"})
            continue
        seen.add(item_id)
        reference = next((_clean(row.get(key)) for key in _REFERENCE_KEYS if _clean(row.get(key))), None)
        load.items.append(
            EvalItem(
                id=item_id, question=question, reference=reference,
                document=_clean(row.get("document")), type=_clean(row.get("type")) or "",
            )
        )
    return load


def resolve_metrics(requested: list[str], items: list[EvalItem]) -> tuple[list[str], list[str]]:
    """Validate metric names; drop reference-based metrics when no item has a reference.

    Returns (metrics to run, notes explaining anything dropped).
    """
    unknown = [name for name in requested if name not in METRICS]
    if unknown:
        raise ValueError(f"Unknown metric(s): {', '.join(unknown)}. Available: {', '.join(METRICS)}")
    notes: list[str] = []
    chosen = list(dict.fromkeys(requested))
    if not any(item.reference for item in items):
        dropped = [name for name in chosen if METRICS[name].needs_reference]
        if dropped:
            notes.append(f"No reference answers in the dataset: skipped {', '.join(dropped)}.")
            chosen = [name for name in chosen if name not in dropped]
    return chosen, notes


# ---------------------------------------------------------------------------
# Running the real pipeline
# ---------------------------------------------------------------------------

class RecordingStore:
    """Wraps a vector store and remembers what each ``query`` returned (everything else passes through)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.retrieved: list = []

    def query(self, question: str, k: int = 5, document_id: str | None = None):
        chunks = self._inner.query(question, k=k, document_id=document_id)
        self.retrieved.extend(chunks)
        return chunks

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def _find_document(documents, name: str):
    wanted = name.strip().lower()
    for doc in documents:
        if wanted in (doc.document_id.lower(), doc.source_file.lower()):
            return doc
    return None


def _compare_text(result) -> str:
    parts = []
    for section in (result.book_a, result.book_b):
        parts.append(f"{section.title}: {section.definition} {section.explanation}".strip())
    parts.append(result.comparison)
    return "\n".join(p for p in parts if p)


def run_item(item: EvalItem, service, recorder: RecordingStore, documents) -> dict:
    """Answer one question like the chat page does. Never raises: a failure becomes ``error``."""
    from app import compare_intent

    recorder.retrieved.clear()
    row = {
        "id": item.id, "type": item.type, "question": item.question, "reference": item.reference,
        "document": item.document, "response": None, "retrieved_contexts": [], "retrieved": [],
        "grounded": None, "route": "chat", "seconds": None, "error": None,
    }
    started = time.monotonic()
    try:
        scope = None
        if item.document:
            doc = _find_document(documents, item.document)
            if doc is None:
                raise LookupError(f"document '{item.document}' is not in the library")
            scope = doc.document_id

        pair = None if scope else compare_intent.detect_compare(item.question, documents)
        if pair is not None:
            row["route"] = "compare"
            result = service.compare_sources(item.question, pair[0].document_id, pair[1].document_id)
            row["response"] = _compare_text(result)
            row["grounded"] = True
        else:
            result = service.answer_question(item.question, scope)
            row["response"] = result.answer
            row["grounded"] = result.grounded
    except Exception as exc:  # noqa: BLE001 - recorded, never scored
        logger.warning("%s failed: %s", item.id, exc)
        row["error"] = f"{type(exc).__name__}: {exc}"

    row["seconds"] = round(time.monotonic() - started, 2)
    row["retrieved_contexts"] = [c.text for c in recorder.retrieved]
    row["retrieved"] = [
        {"source_file": c.source_file, "page": c.page, "chunk_id": c.chunk_id, "score": round(c.score, 4)}
        for c in recorder.retrieved
    ]
    return row


class PipelineUnavailable(RuntimeError):
    """The first questions all failed the same way: a configuration problem, not a bad question."""


MAX_CONSECUTIVE_FAILURES = 3


def generate(
    items: list[EvalItem], service, recorder: RecordingStore, documents,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
) -> list[dict]:
    """Run every question. Stops early if the first ``max_consecutive_failures`` all fail identically
    (wrong API key, no network, unknown model...), instead of spending a whole run to learn that."""
    rows: list[dict] = []
    for index, item in enumerate(items, start=1):
        logger.info("[%d/%d] %s", index, len(items), item.id)
        rows.append(run_item(item, service, recorder, documents))
        recent = rows[-max_consecutive_failures:]
        if (
            len(recent) == max_consecutive_failures
            and all(r["error"] for r in recent)
            and len({r["error"] for r in recent}) == 1
            and len(rows) == len(recent)  # only an unbroken run of failures from the start
        ):
            raise PipelineUnavailable(
                f"The first {max_consecutive_failures} questions failed with the same error, so the run was "
                f"stopped: {recent[0]['error']}"
            )
    return rows


def is_scorable(row: dict) -> bool:
    """A row can be judged only if the pipeline answered and retrieved something."""
    return bool(row.get("response") and not row.get("error") and row.get("retrieved_contexts"))


# ---------------------------------------------------------------------------
# Scoring with RAGAS
# ---------------------------------------------------------------------------

def ensure_ragas_importable() -> None:
    """Make ``import ragas`` work with langchain-community 0.4 and newer.

    ragas 0.4.3 imports ``ChatVertexAI`` / ``VertexAI`` from langchain-community only to list them
    among the model classes it knows about; langchain-community 0.4 removed them, so the import fails
    before any metric is touched. This registers inert placeholders for the two missing names (never
    used by this script, which talks to OpenRouter) so the project does not have to downgrade
    langchain-community. If the import still fails afterwards, the original error is raised.
    """
    try:
        import ragas  # noqa: F401
        return
    except ModuleNotFoundError as exc:
        if "vertexai" not in str(exc).lower():
            raise

    import types

    import langchain_community.llms as llms

    class _Unavailable:  # stands in for a class that langchain-community no longer ships
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Vertex AI is not available in this environment.")

    module = types.ModuleType("langchain_community.chat_models.vertexai")
    module.ChatVertexAI = _Unavailable
    sys.modules["langchain_community.chat_models.vertexai"] = module
    if not hasattr(llms, "VertexAI"):
        llms.VertexAI = _Unavailable
    for name in [n for n in sys.modules if n == "ragas" or n.startswith("ragas.")]:
        del sys.modules[name]  # drop the half-imported package before the retry
    import ragas  # noqa: F401,F811
    logger.info("ragas imported with placeholders for langchain-community's removed Vertex AI classes")


def build_judge_and_metrics(names: list[str]):
    """Create the judge LLM (OpenRouter through the OpenAI-compatible client) and the metrics."""
    ensure_ragas_importable()
    from openai import AsyncOpenAI
    from ragas.embeddings.base import BaseRagasEmbedding
    from ragas.llms import llm_factory
    from ragas.metrics import collections as ragas_metrics

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (the judge LLM uses the same OpenRouter account).")
    model = os.getenv("RAGAS_JUDGE_MODEL") or os.getenv("OPENROUTER_MODEL")
    if not model:
        raise RuntimeError(
            "Set RAGAS_JUDGE_MODEL (or OPENROUTER_MODEL) in .env: a fixed model slug is required so runs are "
            "comparable; 'openrouter/auto' would change the judge between runs."
        )
    client = AsyncOpenAI(api_key=api_key, base_url=os.getenv("OPENROUTER_BASE_URL") or OPENROUTER_BASE_URL)
    max_tokens = int(os.getenv("RAGAS_JUDGE_MAX_TOKENS") or DEFAULT_JUDGE_MAX_TOKENS)
    llm = llm_factory(model, provider="openai", client=client, temperature=0, max_tokens=max_tokens)

    embeddings = None
    if any(METRICS[n].needs_embeddings for n in names):
        from app.nicegui_app.services import backend

        embedder = backend.get_embedder()  # the app's local BGE-M3: no extra API cost

        class ProjectEmbeddings(BaseRagasEmbedding):
            def embed_text(self, text: str, **kwargs):
                return embedder.embed_query(text)

            async def aembed_text(self, text: str, **kwargs):
                return await asyncio.to_thread(embedder.embed_query, text)

        embeddings = ProjectEmbeddings()

    metrics = {}
    for name in names:
        spec = METRICS[name]
        cls = getattr(ragas_metrics, spec.cls)
        metrics[name] = cls(llm=llm, embeddings=embeddings) if spec.needs_embeddings else cls(llm=llm)
    return model, metrics


def _value(result) -> float | None:
    value = getattr(result, "value", result)
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else value


async def score_rows(rows: list[dict], metrics: dict, concurrency: int = 4) -> None:
    """Fill ``row["scores"]`` (metric -> float | None) and ``row["score_errors"]`` for scorable rows.

    A metric that fails or is not applicable (e.g. no reference) is None - never a made-up number.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(row: dict, name: str, metric) -> None:
        spec = METRICS[name]
        values = {
            "user_input": row["question"], "response": row["response"],
            "retrieved_contexts": row["retrieved_contexts"], "reference": row.get("reference"),
        }
        if spec.needs_reference and not row.get("reference"):
            row["scores"][name] = None
            return
        async with semaphore:
            try:
                row["scores"][name] = _value(await metric.ascore(**{key: values[key] for key in spec.inputs}))
            except Exception as exc:  # noqa: BLE001
                row["scores"][name] = None
                row["score_errors"][name] = f"{type(exc).__name__}: {exc}"[:300]

    tasks = []
    for row in rows:
        row["scores"], row["score_errors"] = {}, {}
        if is_scorable(row):
            tasks += [one(row, name, metric) for name, metric in metrics.items()]
    await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def aggregate(rows: list[dict], metric_names: list[str]) -> dict:
    """Mean per metric (over rows that have a score), overall and per question type, plus counts."""
    def summarize(subset: list[dict]) -> dict:
        out = {}
        for name in metric_names:
            values = [r["scores"][name] for r in subset if r.get("scores", {}).get(name) is not None]
            out[name] = {"mean": round(sum(values) / len(values), 4) if values else None, "n": len(values)}
        return out

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["type"] or "(untyped)"].append(row)
    return {
        "overall": summarize(rows),
        "by_type": {kind: summarize(subset) for kind, subset in sorted(by_type.items())},
        "counts": {
            "questions": len(rows),
            "answered": sum(1 for r in rows if r["response"] and not r["error"]),
            "failed": sum(1 for r in rows if r["error"]),
            "not_grounded": sum(1 for r in rows if r["grounded"] is False),
            "no_contexts": sum(1 for r in rows if not r["error"] and not r["retrieved_contexts"]),
            "scored": sum(1 for r in rows if is_scorable(r)),
        },
    }


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_report(meta: dict, summary: dict, rows: list[dict], metric_names: list[str]) -> str:
    counts = summary["counts"]
    lines = [
        f"# RAG evaluation - {meta['run_name']}", "",
        f"- Date (UTC): {meta['timestamp']}",
        f"- Dataset: {meta['dataset']} (sha256 {meta['dataset_sha256'][:12]}…)",
        f"- RAGAS {meta['ragas_version']}; judge model: {meta['judge_model']}; generator model: {meta['generator_model']}",
        f"- Questions: {counts['questions']} | answered {counts['answered']} | failed {counts['failed']} | "
        f"refused (not grounded) {counts['not_grounded']} | scored {counts['scored']}", "",
        "## Scores (mean over rows that could be scored; n = rows used)", "",
        "| metric | mean | n |", "|---|---|---|",
    ]
    for name in metric_names:
        cell = summary["overall"][name]
        lines.append(f"| {name} | {_fmt(cell['mean'])} | {cell['n']} |")
    if len(summary["by_type"]) > 1:
        lines += ["", "## By question type", "", "| type | " + " | ".join(metric_names) + " |",
                  "|---|" + "---|" * len(metric_names)]
        for kind, cells in summary["by_type"].items():
            lines.append(f"| {kind} | " + " | ".join(_fmt(cells[n]["mean"]) for n in metric_names) + " |")
    notes = meta.get("notes") or []
    problems = [r for r in rows if r["error"] or r.get("score_errors")]
    if notes or problems or meta.get("invalid_rows"):
        lines += ["", "## Limitations and problems", ""]
        lines += [f"- {n}" for n in notes]
        lines += [f"- dataset row {i['row']} ignored: {i['reason']}" for i in meta.get("invalid_rows", [])]
        for r in problems:
            if r["error"]:
                lines.append(f"- {r['id']}: pipeline failed ({r['error']})")
            for name, err in (r.get("score_errors") or {}).items():
                lines.append(f"- {r['id']}: {name} failed ({err})")
    return "\n".join(lines) + "\n"


def write_results(out_dir: Path, run_name: str, meta: dict, summary: dict, rows: list[dict], metric_names: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path, md_path = (out_dir / f"{run_name}{ext}" for ext in (".json", ".csv", ".md"))
    json_path.write_text(
        json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    columns = ["id", "type", "question", "reference", "response", "route", "grounded", "error", "seconds",
               *metric_names, "contexts"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            record = {k: row.get(k) for k in columns if k not in metric_names and k != "contexts"}
            record.update({n: (row.get("scores") or {}).get(n) for n in metric_names})
            record["contexts"] = " ||| ".join(row["retrieved_contexts"])
            writer.writerow(record)
    md_path.write_text(render_report(meta, summary, rows, metric_names), encoding="utf-8")
    return [json_path, csv_path, md_path]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate the ChemLib-AI RAG pipeline with RAGAS.")
    p.add_argument("--dataset", required=True, help="JSON or CSV question set (see evaluation/README.md)")
    p.add_argument("--output-dir", default=str(DEFAULT_RESULT_DIR), help="where results are written (default: result/)")
    p.add_argument("--run-name", help="output file stem (default: <dataset>_<UTC timestamp>)")
    p.add_argument("--metrics", default=",".join(DEFAULT_METRICS), help=f"comma separated; available: {', '.join(METRICS)}")
    p.add_argument("--limit", type=int, help="evaluate only the first N questions (cheap smoke run)")
    p.add_argument("--concurrency", type=int, default=4, help="parallel RAGAS judge calls (default 4)")
    p.add_argument("--dry-run", action="store_true", help="validate the dataset and metrics only; no LLM calls")
    p.add_argument("--generate-only", action="store_true", help="run the pipeline and save answers/contexts; skip scoring")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    dataset_path = Path(args.dataset)
    load = load_dataset(dataset_path)
    items = load.items[: args.limit] if args.limit else load.items
    if not items:
        logger.error("No valid questions in %s (%d invalid rows).", dataset_path, len(load.invalid))
        return 2
    metric_names, notes = resolve_metrics([m.strip() for m in args.metrics.split(",") if m.strip()], items)
    for note in notes:
        logger.warning(note)
    logger.info("%d questions (%d invalid rows ignored); metrics: %s", len(items), len(load.invalid), ", ".join(metric_names))
    if args.dry_run:
        return 0

    from app.nicegui_app.services import backend

    store = RecordingStore(backend.get_vector_store())
    documents = store.list_documents()
    if not documents:
        logger.error("The library is empty: index the sample documents first (admin panel or /api/v1/ingest).")
        return 2
    service = backend.make_rag_service(store)
    generator_model = getattr(backend.get_providers()[0], "model_name", "unknown")

    # Build the judge first: a missing key / model / ragas import problem shows up in seconds,
    # not after the whole question set has been answered.
    judge_model, metrics = "(not scored)", {}
    if not args.generate_only:
        judge_model, metrics = build_judge_and_metrics(metric_names)

    try:
        rows = generate(items, service, store, documents)
    except PipelineUnavailable as exc:
        logger.error("%s", exc)
        logger.error("Fix the cause (e.g. OPENROUTER_API_KEY in .env) and run again. Nothing was written.")
        return 1

    if metrics:
        asyncio.run(score_rows(rows, metrics, args.concurrency))

    try:
        ensure_ragas_importable()
        import ragas

        ragas_version = getattr(ragas, "__version__", "unknown")
    except ImportError:  # --generate-only does not need ragas
        ragas_version = "not installed"

    stamp = datetime.now(timezone.utc)
    run_name = args.run_name or f"{dataset_path.stem}_{stamp.strftime('%Y%m%d_%H%M%S')}"
    from rag import rag_service as rs

    meta = {
        "run_name": run_name, "timestamp": stamp.isoformat(timespec="seconds"), "dataset": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "ragas_version": ragas_version, "judge_model": judge_model,
        "generator_model": generator_model, "metrics": metric_names if metrics else [],
        "pipeline": {"chat_top_k": rs.CHAT_TOP_K, "compare_top_k": rs.COMPARE_TOP_K,
                     "similarity_threshold": rs.SIMILARITY_THRESHOLD},
        "library_documents": sorted(d.source_file for d in documents),
        "notes": notes + (["Scoring skipped (--generate-only)."] if args.generate_only else []),
        "invalid_rows": load.invalid,
    }
    summary = aggregate(rows, metric_names if metrics else [])
    for path in write_results(Path(args.output_dir), run_name, meta, summary, rows, metric_names if metrics else []):
        logger.info("wrote %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
