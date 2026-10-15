import pytest

from derle.normalize.tr.text import collapse_ws, fold, tr_lower, tr_title, tr_upper


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ISPARTA", "ısparta"),
        ("İSTANBUL", "istanbul"),
        ("IŞIK", "ışık"),
        ("İĞDIR", "iğdır"),
        ("ÇAĞRI ÖZÜM", "çağrı özüm"),
    ],
)
def test_tr_lower_handles_dotted_and_dotless_i(text: str, expected: str) -> None:
    assert tr_lower(text) == expected


def test_tr_lower_never_produces_combining_dot() -> None:
    # Python's built-in "İ".lower() returns "i̇"; ours must not.
    assert "̇" not in tr_lower("İİİ")
    assert len(tr_lower("İzmir")) == len("İzmir")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("istanbul", "İSTANBUL"), ("ılık", "ILIK"), ("şişli", "ŞİŞLİ"), ("iğne ıslak", "İĞNE ISLAK")],
)
def test_tr_upper(text: str, expected: str) -> None:
    assert tr_upper(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ahmet yılmaz", "Ahmet Yılmaz"),
        ("İBRAHİM IŞIK", "İbrahim Işık"),
        ("ışıl irmak", "Işıl İrmak"),
        ("ali'nin dükkanı", "Ali'nin Dükkanı"),
        ("ayşe-nur  kaya", "Ayşe-Nur Kaya"),
    ],
)
def test_tr_title(text: str, expected: str) -> None:
    assert tr_title(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Şükrü IŞIK", "sukru isik"),
        ("ÇAĞLAR Öğüt", "caglar ogut"),
        ("  Gül   Ünal ", "gul unal"),
        ("Hâlâ", "hala"),
    ],
)
def test_fold(text: str, expected: str) -> None:
    assert fold(text) == expected


def test_collapse_ws_handles_nbsp_and_tabs() -> None:
    assert collapse_ws(" Ahmet\t\tYılmaz \n") == "Ahmet Yılmaz"
