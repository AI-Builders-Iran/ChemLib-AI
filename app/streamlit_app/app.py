"""
DocumentAI: chemistry library app (Streamlit).

Two audiences, one app:

* Users open the app and land on the chat. They see nothing about indexing.
* The library admin opens ``/?mode=admin``, signs in with ADMIN_PASSWORD, and
  gets a second section for adding documents to the vector database.

Run from the project root:
    streamlit run app/streamlit_app/app.py

The original structured-extraction demo now lives in ``extraction_demo.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ROOT_DIR = HERE.parents[1]

# Streamlit runs this file as a script: make `src`, `rag` and `docai_ui` importable.
for path in (str(ROOT_DIR), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Must run before the project modules are imported (OCR reads POPPLER_PATH at import time).
load_dotenv(ROOT_DIR / ".env")

from docai_ui import admin_view, chat_view, components, theme  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="کتابخانهٔ دانشکدهٔ شیمی",
        page_icon="⚗️",
        layout="centered",
    )
    theme.inject()
    st.markdown(components.brand(), unsafe_allow_html=True)

    if not admin_view.is_admin():
        if st.query_params.get("mode") == "admin":
            admin_view.render_login()
        else:
            chat_view.render(is_admin=False)
        return

    if admin_view.render_nav() == admin_view.VIEW_LIBRARY:
        admin_view.render_library()
    else:
        chat_view.render(is_admin=True)


if __name__ == "__main__":
    main()
