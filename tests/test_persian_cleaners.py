"""Persian preprocessing: characters, digits, half-spaces, punctuation, wrapped lines, queries."""

import pytest

from src.processing.cleaners.persian import (
    ZWNJ,
    LineWrapCleaner,
    PersianCharacterCleaner,
    PersianSpacingCleaner,
    normalize_query,
)

chars = PersianCharacterCleaner()
spacing = PersianSpacingCleaner()


# ---------- letters, marks, invisible characters ----------

def test_arabic_letter_variants_become_persian():
    assert chars.clean("علي كتاب") == "علی کتاب"
    assert chars.clean("موسى") == "موسی"


def test_heh_with_yeh_above_is_simplified_in_both_unicode_forms():
    assert chars.clean("خانۀ") == "خانه"            # U+06C0
    assert chars.clean("خانە\u0654") == "خانه"      # what NFKC turns it into


def test_diacritics_and_kashida_are_removed():
    assert chars.clean("مُحَمَّد") == "محمد"
    assert chars.clean("سلـــام") == "سلام"
    assert PersianCharacterCleaner(remove_diacritics=False).clean("مُحَمَّد") == "مُحَمَّد"


def test_bidi_marks_and_bom_are_removed():
    assert chars.clean("\ufeffسلام\u200f دنیا\u200e") == "سلام دنیا"


def test_alef_variants_only_change_when_asked():
    assert chars.clean("أحمد") == "أحمد"
    assert PersianCharacterCleaner(unify_alef=True).clean("أحمد إبراهيم") == "احمد ابراهیم"


# ---------- digits ----------

def test_digits_default_to_latin_and_keep_formulas_intact():
    assert chars.clean("سال ۲۰۲۴ و ٢٠٢٥") == "سال 2024 و 2025"
    assert chars.clean("C6H12O6 و H2O") == "C6H12O6 و H2O"
    assert chars.clean("ثابت ۸٫۳۱۴ و ۵٪") == "ثابت 8.314 و 5%"


def test_persian_digit_mode_leaves_digits_inside_latin_tokens_alone():
    persian = PersianCharacterCleaner(digits="persian")

    assert persian.clean("pH 7 و سال 2024") == "pH ۷ و سال ۲۰۲۴"
    assert persian.clean("C6H12O6 و CO2 و B12") == "C6H12O6 و CO2 و B12"


def test_keep_digits_mode_does_not_touch_digits():
    assert PersianCharacterCleaner(digits="keep").clean("۲۰ و 20 و ٢٠") == "۲۰ و 20 و ٢٠"


def test_invalid_digit_mode_is_rejected():
    with pytest.raises(ValueError):
        PersianCharacterCleaner(digits="arabic")


# ---------- half-space (ZWNJ) ----------

def test_half_space_is_kept_only_between_persian_letters():
    assert chars.clean(f"کتاب{ZWNJ}ها") == f"کتاب{ZWNJ}ها"
    assert chars.clean(f"می{ZWNJ}{ZWNJ}شود") == f"می{ZWNJ}شود"
    assert chars.clean(f"abc{ZWNJ}def") == "abcdef"
    assert chars.clean(f"سلام {ZWNJ}دنیا{ZWNJ}") == "سلام دنیا"
    assert chars.clean(f"۱{ZWNJ}سلام") == f"1سلام"


def test_missing_half_spaces_are_restored():
    assert spacing.clean("می شود") == f"می{ZWNJ}شود"
    assert spacing.clean("نمی توان گفت") == f"نمی{ZWNJ}توان گفت"
    assert spacing.clean("کتاب ها و مقاله های علمی") == f"کتاب{ZWNJ}ها و مقاله{ZWNJ}های علمی"
    assert spacing.clean("بزرگ تر و بزرگ ترین") == f"بزرگ{ZWNJ}تر و بزرگ{ZWNJ}ترین"


def test_half_space_restoration_does_not_touch_words_that_merely_contain_the_pattern():
    assert spacing.clean("دمی گرم") == "دمی گرم"           # "دمی" is not the prefix می
    assert spacing.clean("ما هاله را دید") == "ما هاله را دید"  # ها is only a suffix when it ends the word
    assert spacing.clean("آب تر") == f"آب{ZWNJ}تر"           # known trade-off of the heuristic


def test_persian_punctuation_spacing():
    assert spacing.clean("سلام ، دنیا") == "سلام، دنیا"
    assert spacing.clean("سلام،دنیا") == "سلام، دنیا"
    assert spacing.clean("چیست ؟") == "چیست؟"
    assert spacing.clean("1.5 و 2,5") == "1.5 و 2,5"


# ---------- wrapped lines ----------

WRAPPED = "پیوند کووالانسی پیوندی است که در آن دو اتم\nجفت الکترون را به اشتراک می‌گذارند."


def test_wrapped_sentence_is_joined():
    assert LineWrapCleaner().clean(WRAPPED) == (
        "پیوند کووالانسی پیوندی است که در آن دو اتم جفت الکترون را به اشتراک می‌گذارند."
    )


def test_line_breaks_that_mean_something_are_kept():
    joined_never = [
        "جمله تمام شد و این خط کاملاً بلند است.\nجملهٔ بعدی از اینجا شروع می‌شود.",  # sentence end
        "فصل اول\nپیوند کووالانسی پیوندی است که در آن دو اتم",                        # short heading
        "خط بلندی که هنوز جمله تمام نشده و ادامه دارد\n\nپاراگراف تازه",              # blank line
        "خط بلندی که هنوز جمله تمام نشده و ادامه دارد\n1. مورد اول",                 # list item
        "خط بلندی که مقدمهٔ یک فهرست است و با دونقطه تمام می‌شود:\nمورد اول",         # colon
        "«این جمله با نقل‌قول بسته می‌شود و بلند است.»\nجملهٔ بعدی",                  # closer after period
    ]
    for text in joined_never:
        assert LineWrapCleaner().clean(text) == text


def test_line_wrap_works_for_latin_text_too():
    text = "A covalent bond is a chemical bond that involves\nthe sharing of electron pairs."

    assert LineWrapCleaner().clean(text) == (
        "A covalent bond is a chemical bond that involves the sharing of electron pairs."
    )


# ---------- queries ----------

def test_query_is_normalised_like_the_documents():
    assert normalize_query("اسيد و كربن ؟") == "اسید و کربن؟"
    assert normalize_query("pH آب چقدر است؟ ٧") == "pH آب چقدر است؟ 7"
    assert normalize_query("  می شود  ") == f"می{ZWNJ}شود"
    assert normalize_query("ﻻ") == "لا"  # presentation form, via NFKC


def test_document_and_question_end_up_with_the_same_spelling():
    document_side = spacing.clean(chars.clean("كربن ۱۲ در آبهاي ايران می شود"))

    assert normalize_query("كربن ١٢ در آبهاي ايران می شود") == document_side
