"""ChemLib-AI — NiceGUI application.

Two audiences, one app, exactly like the Streamlit UI it replaces:

* Any visitor can open the app and chat (library or their own private
  documents) — no login required.
* The library admin signs in at ``/login`` with ``ADMIN_PASSWORD`` and gets
  the ability to add/remove documents from the shared library and see
  system status.

Run from the project root:
    python -m app.nicegui_app.main

This module only wires routes and starts the server. It does not contain
any RAG/OCR/ingestion logic — see ``services/backend.py`` for the (thin)
layer that calls the existing ``rag/`` and ``src/`` packages directly, and
``app/api/api_app.py`` for the separate FastAPI surface used by external
API consumers (not used by this UI).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("chemlib_ai.startup")

HERE = Path(__file__).resolve().parent  # app/nicegui_app
ROOT_DIR = HERE.parents[1]

for path in (str(ROOT_DIR),):
    if path not in sys.path:
        sys.path.insert(0, path)

logger.info("[STARTUP] NiceGUI starting…")

# Must run before the project modules are imported (OCR reads POPPLER_PATH,
# PP-Structure reads LAYOUT_ENGINE, etc. at import time).
load_dotenv(ROOT_DIR / ".env")

from nicegui import ui  # noqa: E402

# Importing each page module registers its @ui.page route as a side effect.
# None of this touches the embedding model, the vector store, or an LLM
# provider — those are created lazily, on first real use, by
# services/backend.py (see its module docstring). If startup is ever slow
# again, these page imports are not where to look; the [RAG] log lines from
# services/backend.py and src/embedding/embedding.py are.
from app.nicegui_app.pages import chat, dashboard, documents, login, settings, summary  # noqa: E402,F401

logger.info("[STARTUP] Routes registered: /, /chat, /summary, /documents, /settings, /login")

STORAGE_SECRET = os.getenv("NICEGUI_STORAGE_SECRET") or os.getenv("ADMIN_PASSWORD") or "chemlib-ai-dev-secret"


def run() -> None:
    ui.run(
        title="ChemLib-AI | کتابخانهٔ هوشمند شیمی",
        favicon="⚗️",
        storage_secret=STORAGE_SECRET,
        show=False,
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
