"""
DocumentAI Streamlit demo UI.

Run locally:
    streamlit run app/streamlit_app/app.py

Drives the same DocumentPipeline / DocumentExtractor / providers used by the
FastAPI backend (app/api/api_app.py), so both entry points stay consistent.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

# Make sure `src` is importable when Streamlit runs this file directly.
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.extraction.extractor import DocumentExtractor  # noqa: E402
from src.extraction.providers.gemini_provider import GeminiProvider  # noqa: E402
from src.extraction.providers.openrouter_provider import OpenRouterProvider  # noqa: E402
from src.pipeline import DocumentPipeline  # noqa: E402
from src.schemas.common import DocumentType  # noqa: E402
from src.utils import model_to_dict, model_to_json  # noqa: E402

DOCUMENT_TYPE_LABELS = {
    DocumentType.INVOICE: "🧾 Invoice",
    DocumentType.CONTRACT: "📄 Contract",
    DocumentType.GENERAL: "📁 General document",
}

ENV_KEY_BY_PROVIDER = {
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def build_extractor(provider: str, api_key: str) -> DocumentExtractor:
    if provider == "gemini":
        llm_provider = GeminiProvider(api_key=api_key or None)
    else:
        llm_provider = OpenRouterProvider(api_key=api_key or None)
    return DocumentExtractor(providers=[llm_provider])


def render_sidebar() -> tuple[str, str]:
    st.sidebar.header("⚙️ Model settings")

    provider = st.sidebar.radio(
        "LLM provider",
        options=["gemini", "openrouter"],
        format_func=lambda p: "Google Gemini" if p == "gemini" else "OpenRouter",
    )

    env_var_name = ENV_KEY_BY_PROVIDER[provider]
    has_env_key = bool(os.environ.get(env_var_name))

    st.sidebar.markdown("**API key**")
    api_key = st.sidebar.text_input(
        "Enter your API key to test the pipeline",
        type="password",
        placeholder="your provider key",
        help=(
            "Used only for this session, in memory, to call the model — "
            "never saved to disk or logged. Leave empty to fall back to "
            f"the server's {env_var_name} environment variable, if set."
        ),
    )

    if not api_key and has_env_key:
        st.sidebar.success(f"Using {env_var_name} from the server environment.")
    elif not api_key and not has_env_key:
        st.sidebar.warning("No API key entered and no server-side key found.")

    st.sidebar.divider()
    st.sidebar.caption(
        "Tip: set GEMINI_API_KEY or OPENROUTER_API_KEY as an environment "
        "variable before launching the app to skip this field entirely."
    )

    return provider, api_key


def main():
    st.set_page_config(
        page_title="DocumentAI — Structured Document Extraction",
        page_icon="📑",
        layout="centered",
    )

    st.title("📑 DocumentAI")
    st.caption(
        "Upload an invoice or contract and get clean, validated, structured "
        "JSON back — powered by your choice of LLM (Gemini or OpenRouter)."
    )

    provider, api_key = render_sidebar()

    with st.expander("ℹ️ How this works", expanded=False):
        st.markdown(
            "1. **Load** — the file is parsed (PDF / DOCX / TXT).\n"
            "2. **Clean** — text is normalized (unicode, whitespace, control chars).\n"
            "3. **Chunk & join** — the cleaned text is split and rejoined in order.\n"
            "4. **Extract** — the text is sent to the selected LLM, which "
            "returns fields validated against a Pydantic schema "
            "(Invoice / Contract / GeneralDocument).\n\n"
            "The same `DocumentPipeline` also powers the FastAPI backend "
            "(`app/api/api_app.py`), so both interfaces stay consistent."
        )

    col1, col2 = st.columns(2)
    with col1:
        document_type = st.selectbox(
            "Document type",
            options=list(DOCUMENT_TYPE_LABELS.keys()),
            format_func=lambda dt: DOCUMENT_TYPE_LABELS[dt],
        )
    with col2:
        uploaded_file = st.file_uploader(
            "Document file", type=["pdf", "docx", "txt"], accept_multiple_files=False
        )

    run_clicked = st.button("🚀 Run extraction", type="primary", use_container_width=True)

    if run_clicked:
        if uploaded_file is None:
            st.error("Please upload a file first.")
            return

        tmp_path: Path | None = None
        with st.spinner("Reading, cleaning, and extracting..."):
            try:
                extractor = build_extractor(provider, api_key)
                pipeline = DocumentPipeline(extractor=extractor)

                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = Path(tmp.name)

                result = pipeline.run(tmp_path, document_type)
            except ValueError as exc:
                st.error(f"Could not process this document: {exc}")
                return
            except RuntimeError as exc:
                st.error(f"Extraction failed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                st.error(f"Unexpected error: {exc}")
                return
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)

        st.success("Extraction complete!")

        data = model_to_dict(result)
        st.subheader("Extracted data")
        st.json(data)

        st.download_button(
            "⬇️ Download JSON",
            data=model_to_json(result, indent=2),
            file_name=f"{Path(uploaded_file.name).stem}_extracted.json",
            mime="application/json",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
