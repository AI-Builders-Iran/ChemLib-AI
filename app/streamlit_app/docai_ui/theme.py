"""Visual identity for the library app.

Direction: a chemistry-faculty reading room. Colours come from titration
indicators (methyl orange, bromothymol blue, litmus, phenolphthalein), and the
one memorable element is the *source tile*: every book is drawn like a cell of
the periodic table (colour = book, corner number = page, letters = symbol).
Everything else stays quiet.

The page is right-to-left (Persian first). Streamlit's own layout stays
left-to-right; only the content area is flipped, so widgets keep working.
"""

from __future__ import annotations

import streamlit as st

CSS = """
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

:root {
  --ink: #14263A;
  --paper: #F5F7F6;
  --wash: #E9EEF0;
  --line: #D5DEE2;
  --muted: #5B6B78;
  --endpoint: #B5305F;
  --ok: #2F8F5B;
  --warn: #B26A00;
  --t0: #D9531E;
  --t1: #1F6FB2;
  --t2: #6A4C9C;
  --t3: #B5305F;
  --t4: #2F8F5B;
  --t5: #12808A;
  --font: 'Vazirmatn', 'Vazir', 'Segoe UI', Tahoma, sans-serif;
}

/* ---------- Typography (icons keep their own font: no span/i selectors) ---------- */
.stApp, .stApp button, .stApp input, .stApp textarea, .stApp select,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label {
  font-family: var(--font) !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { line-height: 1.95; }

/* ---------- Chrome we do not need in a client-facing app ---------- */
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
header[data-testid="stHeader"] { display: none; }

/* ---------- Right-to-left content column ---------- */
[data-testid="stMainBlockContainer"], .block-container {
  direction: rtl;
  max-width: 920px !important;
  padding-top: 5rem !important;
  padding-bottom: 7rem !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li,
.dx-user-text, .dx-miss, .dx-hero-text {
  unicode-bidi: plaintext;
  text-align: start;
}
[data-testid="stChatInput"] textarea {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: start;
}

/* ---------- Brand ---------- */
.dx-brand {
  display: flex; align-items: center; gap: 14px;
  padding: 1rem 0 1rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid var(--line);
  overflow: visible;
}
.dx-brand-title {
  font-size: 22px; font-weight: 800; color: var(--ink);
  line-height: 2; padding-top: 4px; overflow: visible;
}
[data-testid="stMarkdownContainer"], [data-testid="stElementContainer"] { overflow: visible !important; }
.dx-brand-sub { font-size: 13.5px; color: var(--muted); line-height: 1.6; }

/* ---------- The source tile (the memorable element) ---------- */
.dx-tile {
  position: relative;
  box-sizing: border-box;
  flex: none;
  width: 96px; height: 108px;
  padding: 26px 6px 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 2px;
  background: #fff;
  border: 1px solid var(--line);
  border-top: 4px solid var(--c, var(--t0));
  border-radius: 3px;
}
.dx-tile-lg { width: 112px; height: 122px; }
.dx-tile-mini { width: 46px; height: 50px; padding: 6px 2px 4px; justify-content: center; }
.dx-tile-brand { width: 54px; height: 58px; padding: 4px 2px; justify-content: center; }
.t0 { --c: var(--t0); } .t1 { --c: var(--t1); } .t2 { --c: var(--t2); }
.t3 { --c: var(--t3); } .t4 { --c: var(--t4); } .t5 { --c: var(--t5); }
.dx-no {
  position: absolute; top: 5px; inset-inline-start: 8px;
  font-size: 12.5px; font-weight: 600; color: var(--muted); line-height: 1.2;
}
.dx-sym { font-size: 30px; font-weight: 800; line-height: 1.15; color: var(--c, var(--t0)); unicode-bidi: plaintext; }
.dx-tile-mini .dx-sym, .dx-tile-brand .dx-sym { font-size: 21px; }
.dx-nm {
  font-size: 11.5px; line-height: 1.5; color: var(--ink); text-align: center; max-width: 100%;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  word-break: break-word; unicode-bidi: plaintext;
}
.dx-tiles { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-top: .5rem; }
.dx-more { align-self: center; font-size: 14px; color: var(--muted); padding: 0 .5rem; }
.dx-shelf-label { font-size: 13.5px; font-weight: 600; color: var(--muted); margin-top: 1.25rem; }
.dx-sources { margin-top: .75rem; }
.dx-sources .dx-shelf-label { margin-top: 0; }

/* ---------- Empty state ---------- */
.dx-hero { padding: 1.25rem 0 .5rem; }
.dx-hero-title { font-size: 30px; font-weight: 800; line-height: 1.6; color: var(--ink); }
.dx-hero-text { font-size: 16px; line-height: 1.95; color: var(--muted); max-width: 62ch; margin: .25rem 0 0; }

/* ---------- Conversation ---------- */
[data-testid="stChatMessage"] { background: transparent; padding: .6rem 0; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: var(--wash); border-radius: 14px; padding: .7rem 1rem;
}
.dx-user-text { font-size: 16.5px; line-height: 1.9; color: var(--ink); }
.dx-miss {
  background: #fff; border: 1px solid var(--line);
  border-inline-start: 4px solid var(--endpoint);
  border-radius: 3px 10px 10px 3px; padding: .7rem 1rem; line-height: 1.9;
}
.dx-hint { font-size: 13.5px; color: var(--muted); margin-top: .5rem; }
.dx-foot { text-align: center; font-size: 12.5px; color: var(--muted); margin-top: 2rem; }

/* ---------- Admin ---------- */
.dx-section-title { font-size: 20px; font-weight: 800; color: var(--ink); margin: 1.75rem 0 .5rem; }
.dx-stats { display: flex; gap: 12px; flex-wrap: wrap; margin: .5rem 0 0; }
.dx-stat { flex: 1 1 160px; background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: .7rem 1rem; }
.dx-stat-value { font-size: 30px; font-weight: 800; line-height: 1.4; color: var(--ink); }
.dx-stat-label { font-size: 13.5px; color: var(--muted); }
.dx-doc-name { font-weight: 600; color: var(--ink); line-height: 1.6; word-break: break-word; unicode-bidi: plaintext; text-align: start; }
.dx-doc-meta { font-size: 13.5px; color: var(--muted); }
.dx-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: .5rem; }
.dx-pill { font-size: 13px; padding: 2px 12px; border-radius: 999px; border: 1px solid; line-height: 1.9; background: #fff; }
.dx-pill.ok { color: var(--ok); border-color: var(--ok); }
.dx-pill.warn { color: var(--warn); border-color: var(--warn); }

[data-testid="stForm"] { background: #fff; border: 1px solid var(--line); border-radius: 10px; }
.stButton > button, .stFormSubmitButton > button { border-radius: 8px; font-weight: 600; }

/* ---------- File uploader, localised (falls back to English if Streamlit changes its markup) ---------- */
[data-testid="stFileUploaderDropzoneInstructions"] > div > span,
[data-testid="stFileUploaderDropzoneInstructions"] > div > small { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] > div::before {
  content: "فایل را اینجا رها کنید"; display: block; font-weight: 600; color: var(--ink);
}
[data-testid="stFileUploaderDropzoneInstructions"] > div::after {
  content: "PDF، DOCX یا TXT"; display: block; font-size: 13px; color: var(--muted);
}
[data-testid="stFileUploaderDropzone"] button { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button::after { content: "انتخاب فایل"; font-size: 14px; }

/* ---------- Motion: respect the user's setting ---------- */
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }

/* ---------- Small screens ---------- */
@media (max-width: 640px) {
  .dx-hero-title { font-size: 24px; }
  .dx-tile-lg { width: 96px; height: 108px; }
}
"""


def inject() -> None:
    """Apply the stylesheet to the current page."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
