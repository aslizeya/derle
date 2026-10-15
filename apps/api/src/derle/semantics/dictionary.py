"""Header vocabulary: how Turkish small businesses actually label their columns.

Keys are folded (see :func:`derle.normalize.tr.text.fold`) so "Müşteri", "MUSTERI" and
"müşteri" all hit the same entry. ``EXACT`` matches the whole header; ``KEYWORDS`` match a
token inside a longer header ("Müşteri Adı Soyadı").
"""

from __future__ import annotations

import re

from derle.domain.models import ColumnRole
from derle.normalize.tr.text import fold

R = ColumnRole

EXACT: dict[str, ColumnRole] = {
    # party
    "musteri": R.PARTY, "musteri adi": R.PARTY, "cari": R.PARTY, "cari adi": R.PARTY,
    "cari hesap": R.PARTY, "ad soyad": R.PARTY, "adi soyadi": R.PARTY, "ad soyadi": R.PARTY,
    "isim": R.PARTY, "isim soyisim": R.PARTY, "kisi": R.PARTY, "firma": R.PARTY,
    "firma adi": R.PARTY, "unvan": R.PARTY, "alici": R.PARTY, "kim": R.PARTY,
    "hesap adi": R.PARTY, "musteri unvani": R.PARTY, "tedarikci": R.PARTY, "name": R.PARTY,
    "customer": R.PARTY,
    # split names
    "ad": R.FIRST_NAME, "adi": R.FIRST_NAME, "first name": R.FIRST_NAME,
    "soyad": R.LAST_NAME, "soyadi": R.LAST_NAME, "soyisim": R.LAST_NAME,
    "last name": R.LAST_NAME,
    # date
    "tarih": R.DATE, "tarihi": R.DATE, "islem tarihi": R.DATE, "gun": R.DATE,
    "vade": R.DATE, "vade tarihi": R.DATE, "fis tarihi": R.DATE, "date": R.DATE,
    # money
    "tutar": R.AMOUNT, "tutari": R.AMOUNT, "fiyat": R.AMOUNT, "ucret": R.AMOUNT,
    "toplam": R.AMOUNT, "toplam tutar": R.AMOUNT, "para": R.AMOUNT, "tl": R.AMOUNT,
    "amount": R.AMOUNT,
    "borc": R.DEBIT, "borcu": R.DEBIT, "veresiye": R.DEBIT, "alinan": R.DEBIT,
    "borc tutari": R.DEBIT, "debit": R.DEBIT,
    "alacak": R.CREDIT, "odeme": R.CREDIT, "odenen": R.CREDIT, "tahsilat": R.CREDIT,
    "yatan": R.CREDIT, "odedigi": R.CREDIT, "credit": R.CREDIT,
    "bakiye": R.BALANCE, "kalan": R.BALANCE, "kalan borc": R.BALANCE, "balance": R.BALANCE,
    # quantity
    "adet": R.QUANTITY, "miktar": R.QUANTITY, "kg": R.QUANTITY, "kilo": R.QUANTITY,
    # contact / identity
    "tel": R.PHONE, "telefon": R.PHONE, "tel no": R.PHONE, "telefon no": R.PHONE,
    "gsm": R.PHONE, "cep": R.PHONE, "cep tel": R.PHONE, "cep telefonu": R.PHONE,
    "phone": R.PHONE,
    "tc": R.TCKN, "tckn": R.TCKN, "tc no": R.TCKN, "tc kimlik": R.TCKN,
    "tc kimlik no": R.TCKN, "kimlik no": R.TCKN,
    "e posta": R.EMAIL, "eposta": R.EMAIL, "mail": R.EMAIL, "email": R.EMAIL,
    # free text
    "aciklama": R.DESCRIPTION, "not": R.DESCRIPTION, "notlar": R.DESCRIPTION,
    "urun": R.DESCRIPTION, "urunler": R.DESCRIPTION, "detay": R.DESCRIPTION,
    "aldigi": R.DESCRIPTION, "aldiklari": R.DESCRIPTION, "mal": R.DESCRIPTION,
    "kategori": R.CATEGORY, "tur": R.CATEGORY, "tip": R.CATEGORY, "grup": R.CATEGORY,
    "islem": R.CATEGORY, "islem turu": R.CATEGORY,
    "no": R.IDENTIFIER, "sira": R.IDENTIFIER, "sira no": R.IDENTIFIER,
    "fis no": R.IDENTIFIER, "fatura no": R.IDENTIFIER, "#": R.IDENTIFIER,
}  # fmt: skip

KEYWORDS: dict[str, ColumnRole] = {
    "musteri": R.PARTY, "cari": R.PARTY, "firma": R.PARTY, "unvan": R.PARTY,
    "tarih": R.DATE,
    "tutar": R.AMOUNT, "fiyat": R.AMOUNT, "toplam": R.AMOUNT,
    "borc": R.DEBIT, "veresiye": R.DEBIT,
    "alacak": R.CREDIT, "odeme": R.CREDIT, "tahsilat": R.CREDIT, "odenen": R.CREDIT,
    "bakiye": R.BALANCE,
    "telefon": R.PHONE, "tel": R.PHONE, "gsm": R.PHONE,
    "tckn": R.TCKN, "kimlik": R.TCKN,
    "aciklama": R.DESCRIPTION, "urun": R.DESCRIPTION, "not": R.DESCRIPTION,
    "kategori": R.CATEGORY,
}  # fmt: skip

_PUNCT = re.compile(r"[^\w#\s]")


def normalize_header(header: str) -> str:
    """ "Müşteri Adı:" -> "musteri adi"; "Tutar (TL)" -> "tutar tl"."""
    return " ".join(_PUNCT.sub(" ", fold(header)).split())


def match_header(header: str) -> tuple[ColumnRole, float, str] | None:
    """Return ``(role, strength, matched_keyword)`` or ``None``.

    Exact matches are strong (0.95); keyword-in-header matches are weaker (0.75). Trailing
    currency hints ("Tutar (TL)") are removed before the exact lookup.
    """
    norm = normalize_header(header)
    if not norm:
        return None
    if norm in EXACT:
        return EXACT[norm], 0.95, norm
    trimmed = re.sub(r"\s+(tl|try|lira)$", "", norm)
    if trimmed in EXACT:
        return EXACT[trimmed], 0.9, trimmed
    for token in norm.split():
        if token in KEYWORDS:
            return KEYWORDS[token], 0.75, token
    return None


TOTAL_ROW_MARKERS = ("toplam", "genel toplam", "ara toplam", "total", "yekun")
