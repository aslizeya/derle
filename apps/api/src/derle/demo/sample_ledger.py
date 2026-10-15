"""A deliberately messy, realistic six-month ledger ("veresiye defteri") with ground truth.

A neighbourhood grocery records credit sales and payments. Every month the file looks
different, because a different family member kept it or a different program exported it:

======  ======================================================================
Ocak    xlsx · title rows · Excel dates and numbers · single "Tutar" column
Şubat   csv ``;`` cp1254 · Turkish numbers · Borç / Ödeme · phone numbers
Mart    xlsx · "Gün / Kim / Ne aldı" · "3 Mart" without year · "1.250 TL"
Nisan   csv ``,`` utf-8 · POS export · ISO dates · English numbers
Mayıs   xlsx · first/last name split · Borç / Alacak · page-break header · total row
Haziran csv ``;`` · "5/6", "15.06.26", "Pazartesi 8 Haziran" · "2 bin", "75 TL"
======  ======================================================================

Customers are written many ways ("Ahmet Yılmaz", "ahmet bey", "A. Yılmaz", "AHMET YILMAZ",
"Yılmaz, Ahmet", typos). Two customers deliberately share a first name, so first-name-only
mentions are genuinely ambiguous. The generator is deterministic for a given seed and returns
the true customer, date and amount for every data row it writes.
"""

from __future__ import annotations

import calendar
import csv
import io
import random
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openpyxl import Workbook

from derle.normalize.tr.text import fold, tr_lower, tr_upper

YEAR = 2026
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran"]
WEEKDAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

MALE = ["Ahmet", "Mehmet", "Mustafa", "Hüseyin", "Hasan", "İbrahim", "Şükrü", "Ömer", "Yusuf",
        "İsmail", "Ali", "Murat", "Osman", "Kemal", "Burak", "Gökhan", "Ümit", "Çağrı", "Erkan",
        "Serkan"]  # fmt: skip
FEMALE = ["Ayşe", "Fatma", "Emine", "Zeynep", "Elif", "Gülşen", "Özge", "Hatice", "Merve",
          "Selin", "Derya", "Sevgi", "İpek", "Şeyma", "Tuğba"]  # fmt: skip
SURNAMES = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın",
            "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt",
            "Özkan", "Şimşek", "Işık", "Güneş", "Erdoğan", "Bulut", "Polat", "Akın"]  # fmt: skip
NOTES = ["manav", "berber", "kasap", "üst kat", "apartman görevlisi", "öğretmen", "eczacı"]
ITEMS = ["ekmek", "süt", "yumurta", "deterjan", "sigara", "çay", "şeker", "peynir", "zeytin",
         "kola", "su", "makarna", "pirinç", "yağ", "gazete", "meyve suyu", "un"]  # fmt: skip
PHONE_PREFIXES = ["530", "532", "533", "535", "536", "541", "542", "505", "506", "555"]


@dataclass(frozen=True, slots=True)
class Customer:
    id: str
    first: str
    last: str
    female: bool
    phone: str | None  # 10 digits
    note: str | None

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


@dataclass(slots=True)
class TruthRow:
    file: str
    sheet: str | None
    row: int
    customer_id: str
    date: str
    amount: str  # positive decimal
    kind: str  # debit | credit
    written_name: str
    duplicate_of_row: int | None = None


@dataclass(slots=True)
class SampleFile:
    name: str
    data: bytes


@dataclass(slots=True)
class SampleLedger:
    files: list[SampleFile]
    truth: list[TruthRow]
    customers: list[Customer]
    seed: int
    meta: dict[str, Any] = field(default_factory=dict)

    def truth_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "customers": [asdict(c) for c in self.customers],
            "rows": [asdict(r) for r in self.truth],
        }


@dataclass(slots=True)
class _Txn:
    customer: Customer
    day: date
    amount: Decimal
    kind: str
    item: str


class _Gen:
    def __init__(self, seed: int, n_customers: int) -> None:
        self.rng = random.Random(seed)
        self.customers = self._customers(n_customers)

    # --- people ---------------------------------------------------------------------------

    def _customers(self, n: int) -> list[Customer]:
        rng = self.rng
        seen: set[tuple[str, str]] = set()
        people: list[tuple[str, str, bool]] = [
            # Deliberate collisions: same first name, and same surname with similar first name.
            ("Mehmet", "Yılmaz", False),
            ("Mehmet", "Demir", False),
            ("Ali", "Kaya", False),
            ("Ayşe", "Kaya", True),
        ]
        seen.update((f, la) for f, la, _ in people)
        while len(people) < n:
            female = rng.random() < 0.45
            first = rng.choice(FEMALE if female else MALE)
            last = rng.choice(SURNAMES)
            if (first, last) not in seen:
                seen.add((first, last))
                people.append((first, last, female))
        customers = []
        for i, (first, last, female) in enumerate(people, start=1):
            phone = None
            if rng.random() < 0.65:
                phone = rng.choice(PHONE_PREFIXES) + f"{rng.randrange(10**7):07d}"
            note = rng.choice(NOTES) if rng.random() < 0.15 else None
            customers.append(Customer(f"C{i:03d}", first, last, female, phone, note))
        return customers

    def written_name(self, c: Customer) -> str:
        """One of the many ways a shopkeeper writes the same person."""
        rng = self.rng
        honorific = "hanım" if c.female else rng.choice(["bey", "bey", "abi", "usta"])
        variants: list[tuple[int, str]] = [
            (34, c.full),
            (10, tr_upper(c.full)),
            (8, fold(c.full)),
            (12, f"{c.first} {honorific}"),
            (8, f"{c.first[0]}. {c.last}"),
            (7, f"{c.first} {self._typo(c.last)}"),
            (5, f"{c.last}, {c.first}"),
            (5, f"{c.full} {honorific.capitalize() if honorific != 'abi' else 'Bey'}"),
            (6 if c.note else 0, f"{c.full} ({c.note})"),
            (5, tr_lower(c.full)),
        ]
        weights = [w for w, _ in variants]
        return rng.choices([v for _, v in variants], weights=weights)[0]

    def _typo(self, word: str) -> str:
        rng = self.rng
        if len(word) < 4:
            return word
        i = rng.randrange(1, len(word) - 1)
        if rng.random() < 0.5:
            return word[:i] + word[i + 1 :]  # drop a letter: Yılmaz -> Yılmz
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]  # swap: Yılmaz -> Yımlaz

    def phone_text(self, c: Customer) -> str | None:
        if c.phone is None or self.rng.random() < 0.25:
            return None  # phone not written on every line
        p = c.phone
        return self.rng.choice(
            [
                f"0{p[:3]} {p[3:6]} {p[6:8]} {p[8:]}",
                f"0{p}",
                f"{p[:3]}-{p[3:6]}-{p[6:]}",
                f"+90 {p[:3]} {p[3:6]} {p[6:8]} {p[8:]}",
            ]
        )

    # --- transactions ---------------------------------------------------------------------

    def month_txns(self, month: int) -> list[_Txn]:
        rng = self.rng
        active = rng.sample(self.customers, k=min(len(self.customers), rng.randint(18, 26)))
        txns: list[_Txn] = []
        first = date(YEAR, month, 1)
        days = calendar.monthrange(YEAR, month)[1]
        for c in active:
            for _ in range(rng.randint(1, 3)):
                day = first + timedelta(days=rng.randrange(days))
                cents = rng.choice([0, 0, 0, 50, rng.randrange(1, 100)])
                amount = Decimal(rng.choice([rng.randint(15, 300), rng.randint(300, 2500)])) + (
                    Decimal(cents) / 100
                )
                txns.append(_Txn(c, day, amount, "debit", rng.choice(ITEMS)))
            if rng.random() < 0.35:
                day = first + timedelta(days=rng.randrange(days))
                pay = Decimal(rng.choice([100, 200, 250, 500, 750, 1000, 1500]))
                txns.append(_Txn(c, day, pay, "credit", "ödeme"))
        txns.sort(key=lambda t: (t.day, t.customer.id))
        return txns


# --- formatting helpers ---------------------------------------------------------------------


def _tr_money(d: Decimal, *, decimals: bool = True) -> str:
    q = f"{d:,.2f}" if decimals else f"{d:,.0f}"
    return q.replace(",", "X").replace(".", ",").replace("X", ".")


def _en_money(d: Decimal) -> str:
    return f"{d:,.2f}"


def _short_money(d: Decimal) -> str:
    """How people actually type amounts: drop ",00", keep real decimals."""
    return _tr_money(d, decimals=d != d.to_integral_value())


def _xlsx(rows: list[list[Any]], sheet: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(rows: list[list[Any]], delimiter: str, encoding: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    for r in rows:
        writer.writerow(["" if v is None else v for v in r])
    return buf.getvalue().encode(encoding)


class _FileBuilder:
    """Collects rows for one file and records ground truth with the real row numbers."""

    def __init__(self, name: str, sheet: str | None, gen: _Gen, dup_rate: float = 0.04) -> None:
        self.name, self.sheet, self.gen = name, sheet, gen
        self.rows: list[list[Any]] = []
        self.truth: list[TruthRow] = []
        self.dup_rate = dup_rate

    def raw(self, row: list[Any]) -> None:
        self.rows.append(row)

    def data(self, row: list[Any], txn: _Txn, written: str) -> None:
        self.rows.append(row)
        original = len(self.rows)
        self.truth.append(self._truth(original, txn, written))
        if self.gen.rng.random() < self.dup_rate:  # typed twice by mistake
            self.rows.append(list(row))
            self.truth.append(self._truth(len(self.rows), txn, written, duplicate_of=original))

    def _truth(
        self, row: int, txn: _Txn, written: str, duplicate_of: int | None = None
    ) -> TruthRow:
        return TruthRow(
            file=self.name,
            sheet=self.sheet,
            row=row,
            customer_id=txn.customer.id,
            date=txn.day.isoformat(),
            amount=str(txn.amount),
            kind=txn.kind,
            written_name=written,
            duplicate_of_row=duplicate_of,
        )


# --- the six months ---------------------------------------------------------------------------


def _ocak(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("ocak_2026.xlsx", "Ocak", gen)
    b.raw(["KARDEŞLER BAKKALİYE — OCAK 2026 VERESİYE DEFTERİ"])
    b.raw([])
    b.raw(["Tarih", "Müşteri", "Tutar", "Açıklama"])
    for t in gen.month_txns(1):
        name = gen.written_name(t.customer)
        amount = float(-t.amount if t.kind == "credit" else t.amount)
        b.data([datetime.combine(t.day, datetime.min.time()), name, amount, t.item], t, name)
    return SampleFile(b.name, _xlsx(b.rows, "Ocak")), b.truth


def _subat(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("subat_2026.csv", None, gen)
    b.raw(["Tarih", "Ad Soyad", "Borç", "Ödeme", "Tel"])
    for t in gen.month_txns(2):
        name = gen.written_name(t.customer)
        debit = _tr_money(t.amount) if t.kind == "debit" else ""
        credit = _tr_money(t.amount) if t.kind == "credit" else ""
        b.data(
            [t.day.strftime("%d.%m.%Y"), name, debit, credit, gen.phone_text(t.customer)], t, name
        )
    return SampleFile(b.name, _csv(b.rows, ";", "cp1254")), b.truth


def _mart(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("mart_2026.xlsx", "Sayfa1", gen)
    b.raw(["Gün", "Kim", "Ne aldı", "Tutar (TL)"])
    for t in gen.month_txns(3):
        name = gen.written_name(t.customer)
        month = gen.rng.choice(["Mart", "mart", "MART"])
        sign = "-" if t.kind == "credit" else ""
        money = f"{sign}{_short_money(t.amount)} TL"
        b.data([f"{t.day.day} {month}", name, t.item, money], t, name)
    return SampleFile(b.name, _xlsx(b.rows, "Sayfa1")), b.truth


def _nisan(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("nisan_2026_pos.csv", None, gen)
    b.raw(["Tarih", "Müşteri Adı", "Tutar", "Telefon"])
    for t in gen.month_txns(4):
        name = gen.written_name(t.customer)
        money = _en_money(-t.amount if t.kind == "credit" else t.amount)
        b.data([t.day.isoformat(), name, money, gen.phone_text(t.customer)], t, name)
    return SampleFile(b.name, _csv(b.rows, ",", "utf-8")), b.truth


def _mayis(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("mayis_2026.xlsx", "Mayıs", gen)
    header = ["Tarih", "Adı", "Soyadı", "Borç", "Alacak"]
    b.raw(header)
    total = Decimal(0)
    for i, t in enumerate(gen.month_txns(5)):
        if i and i % 20 == 0:  # printed in pages: blank line + header again
            b.raw([])
            b.raw(header)
        written = gen.written_name(t.customer)
        first, last = _split_written(written, t.customer)
        day: Any = (
            t.day.strftime("%d.%m.%Y")
            if gen.rng.random() < 0.5
            else datetime.combine(t.day, datetime.min.time())
        )
        debit = float(t.amount) if t.kind == "debit" else None
        credit = float(t.amount) if t.kind == "credit" else None
        total += t.amount if t.kind == "debit" else 0
        b.data([day, first, last, debit, credit], t, written)
    b.raw([])
    b.raw(["TOPLAM", None, None, float(total), None])
    return SampleFile(b.name, _xlsx(b.rows, "Mayıs")), b.truth


def _split_written(written: str, c: Customer) -> tuple[str, str]:
    """Spread a written form over Adı/Soyadı columns the way a person would."""
    if "," in written:
        last, first = (p.strip() for p in written.split(",", 1))
        return first, last
    if "(" in written:
        written = written.split("(", maxsplit=1)[0].strip()
    parts = written.split()
    if len(parts) == 1:
        return parts[0], ""
    if parts[-1].lower() in {"bey", "hanım", "abi", "usta"}:
        return " ".join(parts[:-1]), parts[-1] if len(parts) == 2 else ""
    return " ".join(parts[:-1]), parts[-1]


def _haziran(gen: _Gen) -> tuple[SampleFile, list[TruthRow]]:
    b = _FileBuilder("haziran_2026.csv", None, gen)
    b.raw(["Tarih", "Müşteri", "Tutar", "Not"])
    rng = gen.rng
    for t in gen.month_txns(6):
        name = gen.written_name(t.customer)
        style = rng.random()
        if style < 0.35:
            day = f"{t.day.day}/{t.day.month}"
        elif style < 0.7:
            day = t.day.strftime("%d.%m.%y")
        else:
            day = f"{WEEKDAYS_TR[t.day.weekday()]} {t.day.day} Haziran {YEAR}"
        a = t.amount
        if a == a.to_integral_value() and a % 1000 == 0 and rng.random() < 0.7:
            money = f"{int(a // 1000)} bin"
        elif rng.random() < 0.3:
            money = f"{_short_money(a)} TL"
        else:
            money = _short_money(a)
        if t.kind == "credit":
            money = f"-{money}"
        b.data([day, name, money, t.item if t.kind == "debit" else "ödeme yaptı"], t, name)
    return SampleFile(b.name, _csv(b.rows, ";", "utf-8-sig")), b.truth


MONTH_BUILDERS = [_ocak, _subat, _mart, _nisan, _mayis, _haziran]


def generate(seed: int = 7, n_customers: int = 40) -> SampleLedger:
    gen = _Gen(seed, n_customers)
    files: list[SampleFile] = []
    truth: list[TruthRow] = []
    for build in MONTH_BUILDERS:
        file, rows = build(gen)
        files.append(file)
        truth.extend(rows)
    return SampleLedger(files=files, truth=truth, customers=gen.customers, seed=seed)
