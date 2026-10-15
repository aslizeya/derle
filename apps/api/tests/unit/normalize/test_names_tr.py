import pytest

from derle.normalize.tr.names import parse_name


@pytest.mark.parametrize(
    ("text", "display", "key", "honorifics"),
    [
        ("ahmet bey", "Ahmet", "ahmet", ("bey",)),
        ("Ahmet Yılmaz Bey", "Ahmet Yılmaz", "ahmet yilmaz", ("bey",)),
        ("AYŞE HANIM", "Ayşe", "ayse", ("hanim",)),
        ("ayşe hanım", "Ayşe", "ayse", ("hanim",)),
        ("Mehmet abi", "Mehmet", "mehmet", ("abi",)),
        ("hasan usta", "Hasan", "hasan", ("usta",)),
        ("Sn. Fatma Kaya", "Fatma Kaya", "fatma kaya", ("sn",)),
        ("Dr. İsmail Öztürk", "İsmail Öztürk", "ismail ozturk", ("dr",)),
        ("Bay Ali Can", "Ali Can", "ali can", ("bay",)),
    ],
)
def test_honorifics_are_removed(
    text: str, display: str, key: str, honorifics: tuple[str, ...]
) -> None:
    parsed = parse_name(text)
    assert parsed is not None
    assert parsed.display == display
    assert parsed.key == key
    assert parsed.honorifics == honorifics


def test_lone_honorific_word_is_kept_as_name() -> None:
    # "Bey" alone, or as the first token, is a name (or surname), not a title.
    parsed = parse_name("Bey")
    assert parsed is not None and parsed.display == "Bey"


def test_initials() -> None:
    parsed = parse_name("a. yılmaz")
    assert parsed is not None
    assert parsed.display == "A. Yılmaz"
    assert parsed.key == "a yilmaz"
    assert parsed.has_initials


def test_casing_with_turkish_i() -> None:
    parsed = parse_name("İBRAHİM IŞIK")
    assert parsed is not None
    assert parsed.display == "İbrahim Işık"
    assert parsed.key == "ibrahim isik"


def test_parenthetical_note_is_extracted() -> None:
    parsed = parse_name("Ahmet Yılmaz (manav)")
    assert parsed is not None
    assert parsed.display == "Ahmet Yılmaz"
    assert parsed.note == "manav"


def test_surname_comma_given_name_is_reordered() -> None:
    parsed = parse_name("Yılmaz, Ahmet")
    assert parsed is not None
    assert parsed.display == "Ahmet Yılmaz"
    assert parsed.reordered


def test_company_names_keep_their_words() -> None:
    parsed = parse_name("kardeşler gıda ltd. şti.")
    assert parsed is not None
    assert parsed.is_company
    assert parsed.display == "Kardeşler Gıda Ltd. Şti."


def test_possessive_suffix_is_dropped() -> None:
    parsed = parse_name("Ahmet'in")
    assert parsed is not None and parsed.display == "Ahmet"


@pytest.mark.parametrize("text", ["", "   ", "()"])
def test_empty(text: str) -> None:
    assert parse_name(text) is None
