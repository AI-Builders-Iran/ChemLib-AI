"""Centralized design system — "Academic Library + Chemistry + AI + Enterprise
Dashboard". One accent color (lab teal) carries every interactive moment;
clean cards, subtle shadows, no gradients/neon/glassmorphism. Persian is
right-to-left; NiceGUI/Quasar's own layout stays left-to-right (so the
sidebar, dialogs etc. keep working), only the page content is flipped.

Call :func:`apply` once at the top of every page function (NiceGUI builds the
UI per browser connection, so this runs once per page load — cheap, it only
sets color tokens and injects a stylesheet).
"""

from __future__ import annotations

from nicegui import ui

# ---- Brand / neutrals (kept consistent with the project's other surfaces) ----
INK = "#14263A"
PAPER = "#F6F8F7"
CARD = "#FFFFFF"
WASH = "#EEF2F1"
LINE = "#DEE6E4"
MUTED = "#5B6B78"

BRAND = "#0E7C86"
BRAND_INK = "#0A5A62"
BRAND_WASH = "#E6F2F1"

OK = "#2F8F5B"
WARN = "#B26A00"
DANGER = "#B5305F"

# Source-identity palette (one color per document — periodic-table tiles),
# same hues used by the Streamlit UI so a book's "color identity" is the
# same no matter which UI you're looking at it from.
TILE_COLORS = ["#D9531E", "#1F6FB2", "#6A4C9C", "#B5305F", "#2F8F5B", "#12808A"]

_CSS = f"""
@import url('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css');

body, .q-field__native, .q-item__label {{ font-family: 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif !important; }}
body {{ background: {PAPER}; color: {INK}; }}

/* Persian content reads right-to-left; Quasar's own chrome (drawer side,
   dialogs) is left alone so NiceGUI's layout primitives keep working. */
.dx-rtl {{ direction: rtl; text-align: start; unicode-bidi: plaintext; }}

.dx-card {{
  background: {CARD}; border: 1px solid {LINE}; border-radius: 12px;
  box-shadow: 0 1px 2px rgba(20,38,58,.05);
}}
.dx-muted {{ color: {MUTED}; }}
.dx-brand-text {{ color: {BRAND_INK}; }}

/* ---- Status dot (dashboard / settings system checks) ---- */
.dx-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-inline-end:6px; }}
.dx-dot-ok {{ background: {OK}; }}
.dx-dot-off {{ background: {WARN}; }}

/* ---- Periodic-table style source tile (one per document) ---- */
.dx-tile {{
  box-sizing: border-box; width: 84px; height: 92px; flex: none;
  padding: 20px 6px 6px; display: flex; flex-direction: column; align-items: center;
  justify-content: flex-end; gap: 2px;
  background: {CARD}; border: 1px solid {LINE}; border-top: 4px solid var(--c, {TILE_COLORS[0]});
  border-radius: 8px; position: relative; transition: transform .15s ease, box-shadow .15s ease;
}}
.dx-tile:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(20,38,58,.08); }}
.dx-tile-no {{ position:absolute; top:4px; inset-inline-start:6px; font-size:11px; color:{MUTED}; }}
.dx-tile-sym {{ font-size: 22px; font-weight: 800; line-height: 1.1; color: var(--c, {TILE_COLORS[0]}); }}
.dx-tile-nm {{
  font-size: 10.5px; line-height: 1.35; text-align: center; color: {INK}; max-width: 100%;
  overflow: hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; word-break:break-word;
}}

/* ---- Chat bubbles ---- */
.dx-bubble-user {{
  background: {WASH}; border-radius: 14px; padding: 10px 14px; max-width: 80%;
  margin-inline-start: auto; line-height: 1.9;
}}
.dx-bubble-assistant {{ line-height: 1.95; max-width: 86%; }}
.dx-cite-chip {{
  font-size: 12.5px; padding: 2px 10px; border-radius: 999px; border: 1px solid {LINE};
  background: {CARD}; cursor: pointer; display:inline-flex; align-items:center; gap:4px;
}}
.dx-cite-chip:hover {{ border-color: {BRAND}; color: {BRAND_INK}; }}
.dx-cite-snippet {{
  font-size: 13px; color: {MUTED}; border-inline-start: 3px solid {BRAND_WASH};
  padding-inline-start: 8px; font-style: italic; line-height: 1.8;
}}
"""

_injected = False


def apply() -> None:
    """Set Quasar's color palette and (once per process) inject the stylesheet."""
    global _injected
    ui.colors(
        primary=BRAND,
        secondary=INK,
        accent=BRAND,
        positive=OK,
        negative=DANGER,
        warning=WARN,
        dark=False,
    )
    if not _injected:
        ui.add_css(_CSS)
        _injected = True


def tile_color(seed: str) -> str:
    """Deterministic colour for a document, by name — same mapping idea as
    the Streamlit UI's tile_color_index (not required to match exactly)."""
    return TILE_COLORS[sum(seed.encode("utf-8")) % len(TILE_COLORS)]
