"""Visual identity for ChemLib-AI.

Direction: a chemistry-faculty reading room re-imagined as a modern, premium
research product — "Academic Library + Chemistry + AI + Modern SaaS".
Colours still come from titration indicators (methyl orange, bromothymol
blue, litmus, phenolphthalein) for the *source tiles* (every book is drawn
like a cell of the periodic table: colour = book, corner number = page,
letters = symbol), but the interactive brand accent is now a single lab-teal
so the product reads as one consistent system rather than a rainbow. Deep,
quiet, and confident — not another neon/glassmorphism AI generic.

The page is right-to-left (Persian first). Streamlit's own layout stays
left-to-right; only the content area is flipped, so widgets keep working.
"""

from __future__ import annotations

import streamlit as st

CSS = """
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

:root {
  /* ---- Neutrals (paper / ink) ---- */
  --ink: #14263A;
  --ink-soft: #2C4256;
  --paper: #F6F8F7;
  --card: #FFFFFF;
  --wash: #EEF2F1;
  --line: #DEE6E4;
  --line-soft: #E8EEEC;
  --muted: #5B6B78;
  --muted-soft: #8494A0;

  /* ---- Brand: a single lab-teal accent carries every interactive/CTA moment ---- */
  --brand: #0E7C86;
  --brand-ink: #0A5A62;
  --brand-wash: #E6F2F1;
  --brand-line: #BFDEDC;

  /* ---- Semantic ---- */
  --endpoint: #B5305F;
  --ok: #2F8F5B;
  --ok-wash: #EAF6EF;
  --warn: #B26A00;
  --warn-wash: #FBF2E3;

  /* ---- Source-identity palette (periodic-table tiles) ---- */
  --t0: #D9531E;
  --t1: #1F6FB2;
  --t2: #6A4C9C;
  --t3: #B5305F;
  --t4: #2F8F5B;
  --t5: #12808A;

  --font: 'Vazirmatn', 'Vazir', 'Segoe UI', Tahoma, sans-serif;
  --font-mono: 'JetBrains Mono', 'Courier New', monospace;

  /* ---- Scale ---- */
  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 18px;
  --r-pill: 999px;
  --sh-sm: 0 1px 2px rgba(20, 38, 58, .05);
  --sh-md: 0 6px 20px rgba(20, 38, 58, .07);
  --sh-lg: 0 16px 40px rgba(20, 38, 58, .10);
  --ease: cubic-bezier(.2, .7, .3, 1);
}

/* ================= Base / typography ================= */
.stApp {
  background:
    radial-gradient(1100px 420px at 85% -10%, var(--brand-wash) 0%, transparent 60%),
    var(--paper);
}
.stApp, .stApp button, .stApp input, .stApp textarea, .stApp select,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label {
  font-family: var(--font) !important;
}
.stApp, .stApp p, .stApp li, .stApp label { color: var(--ink); }
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { line-height: 1.95; }
code, pre, kbd { font-family: var(--font-mono) !important; }

/* ---------- Chrome we do not need in a client-facing app ---------- */
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
header[data-testid="stHeader"] { display: none; }

/* ---------- Right-to-left content column ---------- */
[data-testid="stMainBlockContainer"], .block-container {
  direction: rtl;
  max-width: 960px !important;
  padding-top: 1.5rem !important;
  padding-bottom: 7rem !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li,
.dx-user-text, .dx-miss, .dx-hero-text, .dx-compare-def, .dx-compare-exp, .dx-cite-snippet {
  unicode-bidi: plaintext;
  text-align: start;
}
[data-testid="stChatInput"] textarea {
  direction: rtl;
  unicode-bidi: plaintext;
  text-align: start;
}

/* ---------- Nav header (sticky, quiet) ---------- */
.dx-brand {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; gap: 14px;
  padding: 1rem 0;
  margin: 0 0 1.5rem;
  background: color-mix(in srgb, var(--paper) 92%, transparent);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--line);
  overflow: visible;
}
.dx-brand-word { font-family: var(--font-mono); font-size: 20px; font-weight: 700; color: var(--ink);
  letter-spacing: .2px; unicode-bidi: plaintext; direction: ltr; display: inline-block; }
.dx-brand-word b { color: var(--brand-ink); font-weight: 800; }
.dx-brand-title { font-size: 14.5px; font-weight: 600; color: var(--muted); line-height: 1.7; padding-top: 1px; }
[data-testid="stMarkdownContainer"], [data-testid="stElementContainer"] { overflow: visible !important; }
.dx-brand-sub { font-size: 13px; color: var(--muted-soft); line-height: 1.6; }

/* ================= The source tile (the memorable element) ================= */
.dx-tile {
  position: relative;
  box-sizing: border-box;
  flex: none;
  width: 96px; height: 108px;
  padding: 26px 6px 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 2px;
  background: var(--card);
  border: 1px solid var(--line);
  border-top: 4px solid var(--c, var(--t0));
  border-radius: var(--r-sm);
  box-shadow: var(--sh-sm);
  transition: transform .16s var(--ease), box-shadow .16s var(--ease);
}
.dx-tile:hover { transform: translateY(-2px); box-shadow: var(--sh-md); }
.dx-tile-lg { width: 112px; height: 122px; }
.dx-tile-mini { width: 50px; height: 54px; padding: 6px 2px 4px; justify-content: center; }
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
.dx-shelf-label {
  font-size: 12.5px; font-weight: 700; color: var(--muted); margin: 1.5rem 0 .6rem;
  text-transform: uppercase; letter-spacing: .04em;
}
.dx-sources { margin-top: .85rem; }
.dx-sources .dx-shelf-label { margin-top: 0; }

/* ================= Hero / empty state ================= */
.dx-hero { position: relative; padding: .5rem 0 .75rem; overflow: hidden; }
.dx-hero-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12.5px; font-weight: 700; color: var(--brand-ink);
  background: var(--brand-wash); border: 1px solid var(--brand-line);
  border-radius: var(--r-pill); padding: 4px 14px; margin-bottom: .9rem;
  position: relative; z-index: 1;
}
.dx-hero-title {
  font-size: 32px; font-weight: 800; line-height: 1.5; color: var(--ink);
  max-width: 22ch; position: relative; z-index: 1;
}
.dx-hero-text {
  font-size: 16px; line-height: 1.95; color: var(--muted); max-width: 58ch;
  margin: .6rem 0 0; position: relative; z-index: 1;
}
.dx-hero-graphic {
  position: absolute; top: -18px; inset-inline-end: -18px; width: 168px; height: 152px;
  opacity: .9; pointer-events: none; z-index: 0;
}
@media (max-width: 760px) { .dx-hero-graphic { display: none; } }

/* ---------- Suggested-prompt chips (wraps real st.button widgets) ----------
   Scoped to the columns row immediately after the .dx-chip-anchor marker
   (adjacent-sibling), NOT a :has() descendant match — that would reach every
   ancestor block up to the page root and re-style every button on the page. */
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdownContainer"] div.dx-chip-anchor)
  + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button {
  border-radius: var(--r-pill) !important;
  background: var(--card) !important;
  border: 1px solid var(--line) !important;
  color: var(--ink-soft) !important;
  font-size: 13.5px !important;
  font-weight: 600 !important;
  padding: .5rem 1rem !important;
  box-shadow: var(--sh-sm);
  transition: border-color .14s var(--ease), color .14s var(--ease), transform .14s var(--ease);
}
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdownContainer"] div.dx-chip-anchor)
  + div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] > button:hover {
  border-color: var(--brand) !important; color: var(--brand-ink) !important; transform: translateY(-1px);
}

/* ================= Conversation ================= */
[data-testid="stChatMessage"] { background: transparent; padding: .55rem 0; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: var(--wash); border-radius: var(--r-lg); padding: .8rem 1.1rem;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
  padding: .8rem 0 .8rem 0;
}
[data-testid="stChatMessageAvatarAssistant"] {
  background: var(--brand) !important; color: #fff !important;
}
.dx-user-text { font-size: 16.5px; line-height: 1.9; color: var(--ink); }
.dx-miss {
  background: var(--card); border: 1px solid var(--line);
  border-inline-start: 4px solid var(--endpoint);
  border-radius: var(--r-sm) var(--r-md) var(--r-md) var(--r-sm); padding: .8rem 1.1rem; line-height: 1.9;
  box-shadow: var(--sh-sm);
}
.dx-hint { font-size: 13.5px; color: var(--muted); margin-top: .5rem; }
.dx-foot { text-align: center; font-size: 12.5px; color: var(--muted-soft); margin-top: 2.25rem; }

/* ---------- Citation popovers (replaces plain tiles under an answer) ---------- */
div[data-testid="stPopover"] > button {
  border-radius: var(--r-pill) !important;
  background: var(--card) !important;
  border: 1px solid var(--line) !important;
  color: var(--ink-soft) !important;
  font-size: 13px !important;
  padding: .35rem 1rem !important;
  box-shadow: var(--sh-sm);
  transition: border-color .14s var(--ease), transform .14s var(--ease);
}
div[data-testid="stPopover"] > button:hover { border-color: var(--brand) !important; transform: translateY(-1px); }
.dx-cite-snippet {
  font-size: 13.5px; line-height: 1.85; color: var(--muted);
  border-inline-start: 3px solid var(--brand-line); padding-inline-start: .7rem; margin-top: .4rem;
  font-style: italic;
}

/* ---------- Compare-Sources card (two st.columns, each its own section) ---------- */
.dx-compare-section {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r-md);
  padding: 1rem 1.1rem; box-shadow: var(--sh-sm);
}
.dx-compare-title {
  font-size: 14.5px; font-weight: 800; color: var(--brand-ink);
  display: flex; align-items: center; gap: 6px; margin-bottom: .55rem;
  padding-bottom: .5rem; border-bottom: 1px dashed var(--brand-line);
  unicode-bidi: plaintext; text-align: start;
}
.dx-compare-label {
  font-size: 11.5px; font-weight: 700; color: var(--muted-soft); text-transform: uppercase;
  letter-spacing: .04em; margin: .7rem 0 .15rem;
}
.dx-compare-label:first-of-type { margin-top: 0; }
.dx-compare-def, .dx-compare-exp { font-size: 14.5px; line-height: 1.9; color: var(--ink-soft); }
.dx-compare-summary {
  background: var(--brand-wash); border: 1px solid var(--brand-line); border-radius: var(--r-md);
  padding: .9rem 1.1rem; margin-bottom: .85rem; font-size: 15px; line-height: 1.9; color: var(--ink);
}

/* ================= Admin: stats, source cards, status ================= */
.dx-section-title { font-size: 19px; font-weight: 800; color: var(--ink); margin: 2rem 0 .6rem; }
.dx-stats { display: flex; gap: 12px; flex-wrap: wrap; margin: .5rem 0 0; }
.dx-stat {
  flex: 1 1 160px; background: var(--card); border: 1px solid var(--line); border-radius: var(--r-md);
  padding: .85rem 1.1rem; box-shadow: var(--sh-sm);
}
.dx-stat-value { font-size: 28px; font-weight: 800; line-height: 1.4; color: var(--ink); }
.dx-stat-label { font-size: 13px; color: var(--muted); }
.dx-doc-name { font-weight: 700; color: var(--ink); line-height: 1.6; word-break: break-word; unicode-bidi: plaintext; text-align: start; }
.dx-doc-meta { font-size: 13px; color: var(--muted); margin-top: 2px; }
.dx-doc-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.dx-badge {
  font-size: 11.5px; font-weight: 700; padding: 2px 10px; border-radius: var(--r-pill);
  background: var(--wash); color: var(--muted); border: 1px solid var(--line-soft);
}
.dx-badge.ok { background: var(--ok-wash); color: var(--ok); border-color: transparent; }
.dx-pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: .5rem; }
.dx-pill { font-size: 13px; padding: 3px 12px; border-radius: var(--r-pill); border: 1px solid; line-height: 1.9; background: var(--card); }
.dx-pill.ok { color: var(--ok); border-color: var(--ok); }
.dx-pill.warn { color: var(--warn); border-color: var(--warn); }

[data-testid="stForm"] {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--sh-sm);
  padding-top: .25rem;
}
[data-testid="stContainer"] { border-radius: var(--r-md) !important; }
.stButton > button, .stFormSubmitButton > button { border-radius: var(--r-sm); font-weight: 700; }
.stFormSubmitButton > button[kind="primary"], .stButton > button[kind="primary"] {
  background: var(--brand) !important; border-color: var(--brand) !important;
}
.stFormSubmitButton > button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover {
  background: var(--brand-ink) !important; border-color: var(--brand-ink) !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"] { padding: 2px 4px; }

/* ---------- Alerts, unified with the rest of the system ---------- */
[data-testid="stAlert"] { border-radius: var(--r-md) !important; border: 1px solid var(--line-soft); box-shadow: var(--sh-sm); }

/* ---------- File uploader → "dropzone", localised ---------- */
[data-testid="stFileUploaderDropzone"] {
  border-radius: var(--r-md) !important;
  border: 1.5px dashed var(--brand-line) !important;
  background: var(--brand-wash) !important;
  transition: border-color .14s var(--ease), background .14s var(--ease);
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--brand) !important; }
[data-testid="stFileUploaderDropzoneInstructions"] > div > span,
[data-testid="stFileUploaderDropzoneInstructions"] > div > small { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] > div::before {
  content: "فایل را اینجا رها کنید"; display: block; font-weight: 700; color: var(--ink);
}
[data-testid="stFileUploaderDropzoneInstructions"] > div::after {
  content: "PDF، DOCX یا TXT"; display: block; font-size: 13px; color: var(--muted);
}
[data-testid="stFileUploaderDropzone"] button { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button::after {
  content: "انتخاب فایل"; font-size: 14px; color: var(--brand-ink) !important; font-weight: 700;
}

/* ---------- Progress bar ---------- */
[data-testid="stProgress"] > div > div > div { background: var(--brand) !important; }

/* ---------- Motion: subtle only, and respect the user's setting ---------- */
[data-testid="stChatMessage"], .dx-tile, .dx-compare-section, .dx-stat { animation: dxFadeUp .22s var(--ease) both; }
@keyframes dxFadeUp { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }

/* ---------- Small screens ---------- */
@media (max-width: 640px) {
  .dx-hero-title { font-size: 24px; max-width: none; }
  .dx-tile-lg { width: 96px; height: 108px; }
}
"""


def inject() -> None:
    """Apply the stylesheet to the current page."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
