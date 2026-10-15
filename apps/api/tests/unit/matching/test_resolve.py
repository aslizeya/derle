from derle.matching.blocking import candidate_pairs
from derle.matching.profiles import Mention, Profile, build_profiles
from derle.matching.resolve import Decision, Resolution, resolve


def profiles_of(*names: str | tuple[str, str]) -> list[Profile]:
    mentions = []
    for i, n in enumerate(names):
        name, phone = (n, None) if isinstance(n, str) else n
        mentions.append(Mention(record_id=i, name=name, phone=phone))
    return build_profiles(mentions)


def groups(profiles: list[Profile], result: Resolution) -> set[frozenset[str]]:
    return {frozenset(profiles[i].key for i in c) for c in result.clusters}


def test_identical_names_share_one_profile() -> None:
    profiles = profiles_of("Ahmet Yılmaz", "AHMET YILMAZ", "ahmet yilmaz")
    assert len(profiles) == 1
    assert profiles[0].record_ids == [0, 1, 2]


def test_unique_partial_name_is_merged() -> None:
    profiles = profiles_of("Derya Demir", "D. Demir", "Kemal Polat", "Kemal")
    result = resolve(profiles)
    assert groups(profiles, result) == {
        frozenset({"derya demir", "d demir"}),
        frozenset({"kemal polat", "kemal"}),
    }
    assert result.review == []


def test_ambiguous_partial_name_becomes_one_card_per_owner() -> None:
    profiles = profiles_of("Mehmet Yılmaz", "Murat Yılmaz", "M. Yılmaz")
    result = resolve(profiles)
    assert len(result.clusters) == 3
    pairs = {frozenset((profiles[r.a].key, profiles[r.b].key)) for r in result.review}
    assert pairs == {
        frozenset({"m yilmaz", "mehmet yilmaz"}),
        frozenset({"m yilmaz", "murat yilmaz"}),
    }


def test_same_decision_merges_and_removes_card() -> None:
    profiles = profiles_of("Mehmet Yılmaz", "Murat Yılmaz", "M. Yılmaz")
    decision = Decision("m yilmaz|", "mehmet yilmaz|", "same")
    result = resolve(profiles, [decision])
    assert frozenset({"m yilmaz", "mehmet yilmaz"}) in groups(profiles, result)
    assert result.review == []  # "m yilmaz" is anchored now; the Murat card is moot


def test_different_decision_blocks_even_an_automatic_merge() -> None:
    profiles = profiles_of("Ahmet Yılmaz", "Ahmet Yılmz")
    assert len(resolve(profiles).clusters) == 1
    result = resolve(profiles, [Decision("ahmet yilmaz|", "ahmet yilmz|", "different")])
    assert len(result.clusters) == 2
    assert result.blocked_by_decision == 1
    assert result.review == []


def test_cannot_link_holds_transitively() -> None:
    # A~B and B~C would chain A and C together; the user said A and C differ.
    profiles = profiles_of("Ahmet Yılmaz", "Ahmet Yılmz", "Ahmet Ylmz")
    result = resolve(profiles, [Decision("ahmet yilmaz|", "ahmet ylmz|", "different")])
    for cluster in groups(profiles, result):
        assert not {"ahmet yilmaz", "ahmet ylmz"} <= cluster


def test_skip_hides_the_card_without_constraining() -> None:
    profiles = profiles_of("Ahmet Yılmaz", "A. Yılmaz", "Ali Yılmaz")
    first = resolve(profiles)
    assert first.review
    skip = [Decision(profiles[r.a].id, profiles[r.b].id, "skip") for r in first.review]
    assert resolve(profiles, skip).review == []


def test_phone_links_different_spellings() -> None:
    profiles = profiles_of(("Ahmet", "05321234567"), ("Ahmet Yılmaz", "0532 123 45 67"))
    assert len(resolve(profiles).clusters) == 1


def test_decisions_about_vanished_profiles_are_ignored() -> None:
    profiles = profiles_of("Ahmet Yılmaz")
    result = resolve(profiles, [Decision("ghost|", "ahmet yilmaz|", "same")])
    assert len(result.clusters) == 1


def test_blocking_skips_unrelated_names_but_keeps_initials() -> None:
    profiles = profiles_of("Ahmet Yılmaz", "A. Yılmaz", "Zeynep Kara")
    pairs = {frozenset((profiles[i].key, profiles[j].key)) for i, j in candidate_pairs(profiles)}
    assert frozenset({"ahmet yilmaz", "a yilmaz"}) in pairs
    assert not any("zeynep kara" in p for p in pairs)
