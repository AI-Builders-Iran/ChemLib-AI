# RAG evaluation with RAGAS

Evaluates the application's **real** pipeline: `RAGService` over the library's own vector store,
routed like the chat page (document scope, or "compare A and B" detection). The retriever is wrapped
by a recorder, so the contexts RAGAS judges are exactly the chunks the LLM received.

## Setup

```bash
pip install -r requirements.txt -r requirements-eval.txt
```
The script copes with `langchain-community` 0.4+ (which ragas 0.4.3 cannot import on its own); no downgrade needed.
`.env` (besides the usual `OPENROUTER_API_KEY`): `RAGAS_JUDGE_MODEL=<openrouter model slug>`.

A wrong `OPENROUTER_API_KEY` (HTTP 401) stops the run after the first 3 questions with nothing written; the judge is
built before any question is asked, so ragas / judge-model problems show up immediately.

The sample documents must already be indexed in the library (admin panel or `/api/v1/ingest`).

## Run

```bash
python -m evaluation.evaluate_rag --dataset evaluation/datasets/<name>.json --dry-run   # validate only, free
python -m evaluation.evaluate_rag --dataset evaluation/datasets/<name>.json --limit 5   # cheap smoke run
python -m evaluation.evaluate_rag --dataset evaluation/datasets/<name>.json             # full run
python -m evaluation.evaluate_rag --dataset ... --generate-only                         # answers + contexts, no judge cost
```
Options: `--metrics faithfulness,context_recall`, `--output-dir`, `--run-name`, `--concurrency`.

Output in `result/`: `<run>.json` (everything: meta, per-question answers, contexts, scores, errors),
`<run>.csv`, `<run>.md` (readable report). The meta records the dataset hash, RAGAS version, judge and
generator models, retrieval settings and the library's document list, so a run can be repeated.

## Dataset format

JSON (a list, or `{"questions": [...]}`) or CSV with a header row:

| field | required | meaning |
|---|---|---|
| `question` | yes | the question, as a user would type it |
| `ground_truth` (or `reference`) | no | reference answer, written from the real document text |
| `id` | no | unique id (default `q001`, `q002`, ...) |
| `document` | no | restrict to one library document (file name or id); leave empty to search the whole library |
| `type` | no | free label, e.g. `direct`, `multi_step`, `table`, `comparison`; results are also averaged per type |
| `evidence`, `review_note` | no | for human review only (where the answer is in the source, what to double-check); the script ignores them |

Comparison questions should name both sources in the question text (as in chat, "Compare these sources: A and B").
Invalid rows (no question, duplicate id) are skipped and listed in the report.

## Metrics (RAGAS 0.4, `ragas.metrics.collections`)

| metric | needs | judge embeddings |
|---|---|---|
| `faithfulness` | question, answer, contexts | no |
| `answer_relevancy` | question, answer | yes |
| `context_precision` | question, reference, contexts | no |
| `context_recall` | question, reference, contexts | no |
| `answer_correctness` | question, answer, reference | yes |

Metrics that need a reference are dropped when the dataset has none, and skipped (`n/a`) for rows without one.
Embeddings reuse the app's local BGE-M3, so they cost no API calls.

## Cost and limits

- Each question costs the app's own LLM calls plus several judge calls per metric. Use `--limit` first.
- A question the pipeline failed on, or that retrieved nothing, is recorded and **not scored**.
- A refused answer ("insufficient information") is scored as it is; faithfulness on a refusal can be `n/a`.
- RAGAS prompts are English; judging Persian text depends on the judge model's Persian ability.
- Judge errors and `NaN` become `n/a` with the error stored; they are never replaced by a number.
- The generator's temperature is not set by the app, so repeated runs can differ slightly.

## Included dataset: `datasets/chemlib_sample_v1.json`

40 questions written from six real sample documents (a Persian TXT, an English text PDF, and four scanned
English PEP reports). Types: 18 direct, 11 multi-step, 8 table, 3 comparison. `document` holds the exact file
name, so the six files must be indexed under those names (or edit the field). Comparison questions have no
`document` and name both sources in the text, so they take the chat's compare route.
Reference answers were written by reading the documents (text layer for the TXT/PDF, page images for the scans);
rows with a `review_note` are the ones to double-check against the originals.
