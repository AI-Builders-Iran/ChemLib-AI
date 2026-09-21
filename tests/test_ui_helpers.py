"""Pure UI logic: labels, tiles, escaping and the admin password check."""

from docai_ui import auth, components
from docai_ui.helpers import (
    TILE_COLOR_COUNT,
    display_name,
    element_symbol,
    page_label,
    tile_color_index,
    to_fa_digits,
    unique_sources,
)


def test_persian_digits():
    assert to_fa_digits(2024) == "۲۰۲۴"
    assert to_fa_digits("p.7") == "p.۷"


def test_page_label_is_one_based_and_empty_without_page():
    assert page_label(0) == "۱"
    assert page_label(41) == "۴۲"
    assert page_label(None) == ""


def test_element_symbol_latin_and_persian():
    assert element_symbol("Organic_Chemistry.pdf") == "Or"
    assert element_symbol("chem_intro.pdf") == "Ch"
    assert element_symbol("شیمی_آلی.pdf") == "شی"
    assert element_symbol("X.txt") == "X"
    assert element_symbol("123.pdf") == "12"


def test_display_name_drops_extension_and_underscores():
    assert display_name("Organic_Chemistry_Vol1.pdf") == "Organic Chemistry Vol1"
    assert display_name("جزوه_آلی.docx") == "جزوه آلی"


def test_tile_color_is_stable_and_in_range():
    assert tile_color_index("a.pdf") == tile_color_index("a.pdf")
    assert all(0 <= tile_color_index(f"book{i}.pdf") < TILE_COLOR_COUNT for i in range(50))


def test_unique_sources_dedupes_and_sorts():
    result = unique_sources(
        [
            {"file": "b.pdf", "page": 3},
            {"file": "a.pdf", "page": None},
            {"file": "b.pdf", "page": 3},
            {"file": "a.pdf", "page": 1},
        ]
    )

    assert result == [
        {"file": "a.pdf", "page": None},
        {"file": "a.pdf", "page": 1},
        {"file": "b.pdf", "page": 3},
    ]


def test_source_tile_shows_the_human_page_and_escapes_the_file_name():
    html = components.sources_row([{"file": '<img src=x onerror=alert(1)>.pdf', "page": 6}])

    assert "<img" not in html
    assert "&lt;img" in html
    assert ">۷<" in html  # stored page 6 -> page 7


def test_user_text_is_shown_literally():
    html = components.user_text("<script>alert(1)</script>\nsecond line")

    assert "<script>" not in html
    assert "<br>" in html


def test_components_are_single_block_html():
    """Markdown splits HTML blocks at blank lines, so fragments must not contain any."""
    fragments = [
        components.brand(),
        components.hero([("1", "a.pdf"), ("2", "b.pdf")]),
        components.empty_library(True),
        components.sources_row([{"file": "a.pdf", "page": 1}]),
        components.not_found("nothing"),
        components.stats_row([("x", 1)]),
        components.status_pills([("k", True), ("m", False)]),
    ]
    for html in fragments:
        assert "\n" not in html


def test_hero_summarises_books_beyond_the_shelf_limit():
    documents = [(str(i), f"book{i}.pdf") for i in range(components.SHELF_LIMIT + 3)]

    assert components.hero(documents).count('class="dx-tile ') == components.SHELF_LIMIT
    assert "۳ منبع دیگر" in components.hero(documents)


def test_admin_password_check(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert auth.admin_configured() is False
    assert auth.verify_admin_password("anything") is False
    assert auth.verify_admin_password("") is False

    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-رمز")
    assert auth.admin_configured() is True
    assert auth.verify_admin_password("s3cret-رمز") is True
    assert auth.verify_admin_password("wrong") is False


def test_private_hero_states_that_documents_stay_in_memory():
    empty = components.private_hero([])
    filled = components.private_hero([("1", "my_notes.pdf")])

    assert "فقط در حافظهٔ همین صفحه" in empty
    assert "dx-tile" not in empty
    assert "dx-tile" in filled and "my notes" in filled
    assert "\n" not in empty and "\n" not in filled
