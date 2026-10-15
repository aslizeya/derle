"""Turkish name-matching edge cases. Every case states why the expected band is right."""

import math

import pytest

from derle.matching.profiles import Mention, Profile, build_profiles, name_key, phone_key
from derle.matching.scoring import score_pair, with_unique_completion


def profile(name: str, phone: str | None = None) -> Profile:
    (p,) = build_profiles([Mention(record_id=1, name=name, phone=phone)])
    return p


def band(a: str, b: str, phone_a: str | None = None, phone_b: str | None = None) -> str:
    return score_pair(profile(a, phone_a), profile(b, phone_b)).band


def codes(a: str, b: str, phone_a: str | None = None, phone_b: str | None = None) -> list[str]:
    match = score_pair(profile(a, phone_a), profile(b, phone_b))
    return [e.code for e in match.evidence]


def test_folding_makes_turkish_spellings_identical() -> None:
    assert name_key("Şükrü IŞIK") == name_key("sukru isik") == "sukru isik"
    assert band("Şükrü Işık", "SUKRU ISIK") == "auto"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Ahmet Yılmaz", "Ahmet Yılmz"),  # dropped letter in a long word
        ("Mehmet Demir", "Mehmet Demri"),  # swapped neighbours
        ("Şükrü Kaya", "Şükrü Kyaa"),  # swap is safe even in a short word
        ("Selin Çetin", "Selin Çeitn"),
        ("Ali Bulut", "Ali Bult"),
    ],
)
def test_single_typos_merge_automatically(a: str, b: str) -> None:
    assert band(a, b) == "auto"
    assert "typo" in codes(a, b)


def test_substituted_letter_in_short_surname_is_a_different_family() -> None:
    # Kaya and Kara are both common surnames; one changed letter is not a typo signal.
    assert band("Ali Kaya", "Ali Kara") != "auto"


@pytest.mark.parametrize(
    ("a", "b", "code"),
    [
        ("A. Yılmaz", "Ahmet Yılmaz", "initials_match"),
        ("Ahmet", "Ahmet Yılmaz", "first_name_only"),
    ],
)
def test_partial_names_go_to_review(a: str, b: str, code: str) -> None:
    assert band(a, b) == "review"
    assert codes(a, b)[0] == code


def test_partial_name_with_same_phone_is_automatic() -> None:
    assert band("Ahmet", "Ahmet Yılmaz", "0532 123 45 67", "05321234567") == "auto"


def test_unique_completion_lifts_a_partial_name_over_the_threshold() -> None:
    match = score_pair(profile("A. Yılmaz"), profile("Ahmet Yılmaz"))
    boosted = with_unique_completion(match)
    assert boosted.band == "auto"
    assert boosted.evidence[-1].code == "unique_completion"


@pytest.mark.parametrize(
    ("a", "b", "code"),
    [
        ("Mehmet Yılmaz", "Mehmet Demir", "surname_conflict"),
        ("Ali Kaya", "Ayşe Kaya", "first_name_conflict"),
        ("Ahmet Yılmaz", "Mehmet Yılmaz", "first_name_conflict"),
        ("S. Kara", "Z. Kara", "first_name_conflict"),
    ],
)
def test_conflicting_parts_mean_different_people(a: str, b: str, code: str) -> None:
    assert band(a, b) == "different"
    assert code in codes(a, b)


def test_same_name_different_phone_is_not_merged() -> None:
    assert band("Ahmet Yılmaz", "Ahmet Yılmaz", "05321112233", "05554443322") != "auto"
    assert "phone_conflict" in codes("Ahmet Yılmaz", "Ahmet Yılmaz", "05321112233", "05554443322")


def test_evidence_weights_add_up_to_the_score() -> None:
    match = score_pair(profile("Ahmet", "05321234567"), profile("Ahmet Yılmaz", "05321234567"))
    logit = sum(e.weight for e in match.evidence)
    assert match.score == pytest.approx(1 / (1 + math.exp(-logit)), abs=1e-3)


def test_phone_key_ignores_formatting() -> None:
    assert phone_key("+90 (532) 123-45-67") == phone_key("0532 123 45 67") == "5321234567"
    assert phone_key("123") is None
