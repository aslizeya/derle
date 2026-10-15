import pytest

from derle.domain.models import ColumnInference, ColumnRole
from derle.semantics.dictionary import match_header, normalize_header
from derle.semantics.infer import infer_column, resolve_conflicts

R = ColumnRole


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("Tarih", R.DATE),
        ("İŞLEM TARİHİ", R.DATE),
        ("Müşteri Adı", R.PARTY),
        ("MUSTERI", R.PARTY),
        ("Ad Soyad", R.PARTY),
        ("Tutar (TL)", R.AMOUNT),
        ("Tutar TL", R.AMOUNT),
        ("Borç", R.DEBIT),
        ("Ödeme", R.CREDIT),
        ("Tahsilat", R.CREDIT),
        ("Kalan Borç", R.BALANCE),
        ("Cep Tel.", R.PHONE),
        ("T.C. Kimlik No", R.TCKN),
        ("Açıklama", R.DESCRIPTION),
        ("Soyadı", R.LAST_NAME),
    ],
)
def test_header_vocabulary(header: str, role: ColumnRole) -> None:
    hit = match_header(header)
    assert hit is not None
    assert hit[0] == role


def test_normalize_header() -> None:
    assert normalize_header("  Müşteri Adı: ") == "musteri adi"
    assert normalize_header("Tutar (TL)") == "tutar tl"


def test_header_and_values_agree() -> None:
    inf = infer_column(0, "Tarih", ["01.03.2026", "2 Mart 2026", "03/03/2026"])
    assert inf.role == R.DATE
    assert inf.confidence > 0.9
    assert [r.code for r in inf.reasons] == ["header_match", "values_fit"]


def test_values_alone_without_header() -> None:
    assert infer_column(0, "#1", ["01.03.2026", "02.03.2026"]).role == R.DATE
    assert infer_column(1, "#2", ["0532 123 45 67", "05551112233"]).role == R.PHONE
    assert infer_column(2, "#3", ["1.250,00", "80", "45,5"]).role == R.AMOUNT
    assert infer_column(3, "#4", ["Ahmet Yılmaz", "Ayşe Kaya", "Ahmet Yılmaz"]).role == R.PARTY
    assert infer_column(4, "#5", ["10000000146", "10000000146"]).role == R.TCKN


def test_values_override_contradicting_header() -> None:
    inf = infer_column(0, "Tutar", ["01.03.2026", "02.03.2026", "03.03.2026", "04.03.2026"])
    assert inf.role == R.DATE
    assert "values_override" in [r.code for r in inf.reasons]


def test_unknown_header_with_mixed_values_is_low_confidence() -> None:
    inf = infer_column(0, "xyz", ["a1", "b2", "c3"])
    assert inf.confidence < 0.6


def test_only_one_party_column_survives() -> None:
    a = ColumnInference(col_index=0, header="Müşteri", role=R.PARTY, confidence=0.9)
    b = ColumnInference(col_index=1, header="Kişi", role=R.PARTY, confidence=0.6)
    out = resolve_conflicts([a, b])
    assert [i.role for i in out] == [R.PARTY, R.DESCRIPTION]
