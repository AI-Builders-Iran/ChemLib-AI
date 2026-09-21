import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "app" / "streamlit_app"

# `src`, `rag` live at the project root; `docai_ui` next to the Streamlit entry point.
for path in (ROOT, UI_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
