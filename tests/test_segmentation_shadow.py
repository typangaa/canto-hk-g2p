"""
Segmentation-shadow pruning regression suite (v2.3.0).

Root cause: rime-cantonese's words.dict.yaml is an IME phrase-completion
list, not a pure lexicon — a large fraction of its entries are "purely
compositional" (their reading is exactly the char-by-char concatenation of
each character's own solo reading, e.g. "我瞓" = "ngo5 fan3" =
char_entries['我'] + char_entries['瞓']). Kept in the segmentation dict,
these entries still resolve correctly when matched on their own, but their
PRESENCE greedily consumes a prefix of the string via the segmenter's
leftmost-longest-match, so a real compound starting at the swallowed
character never gets a chance to match. The orphaned trailing character then
falls into ambiguous "ranked"-confidence char fallback instead of the
correct word-level reading.

The canonical case (surfaced via HKCanCor corpus review, 2026-07-21): "我瞓"
(a rime IME-phrase entry, ngo5 fan3 — pure composition of 我+瞓) blocked
"瞓覺" (fan3 gaau3, "to sleep") from ever matching, orphaning "覺" into its
ambiguous char-level default gok3 ("to feel") instead of the correct gaau3.

Fix: scripts/build_dict.py::prune_compositional_word_entries() removes every
purely-compositional word_entries key (except oral_hk.tsv / variant_words.tsv
/ tone_sandhi_words.tsv entries, and anything carrying genuine word-level
candidate ambiguity) from the SEGMENTATION dict, verified via a fixed-point
simulation that the entry's own reading is unchanged by its removal. This is
a structural fix for the whole bug class, not a per-word patch — see
CHANGELOG for the before/after scope (~79,600 pruned entries) and the
introspection-granularity tradeoff (convert() output is unaffected;
convert_detailed()/convert_candidates() token boundaries for previously-
compositional words now reflect per-character resolution).
"""
import pytest

from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# (input text, expected full jyutping output)
FAN3_GAAU3_GOLD_SENTENCES = [
    ("瞓覺", "fan3 gaau3"),
    ("去瞓覺喇", "heoi3 fan3 gaau3 laa3"),
    ("我瞓覺先", "ngo5 fan3 gaau3 sin1"),
    ("你瞓覺未", "nei5 fan3 gaau3 mei6"),
    ("要瞓覺喇", "jiu3 fan3 gaau3 laa3"),
    ("仲未瞓覺", "zung6 mei6 fan3 gaau3"),
    ("今日好早瞓覺", "gam1 jat6 hou2 zou2 fan3 gaau3"),
    ("快啲瞓覺", "faai3 di1 fan3 gaau3"),
]


@pytest.mark.parametrize(
    "text,expected", FAN3_GAAU3_GOLD_SENTENCES, ids=[t for t, _ in FAN3_GAAU3_GOLD_SENTENCES]
)
def test_fan3_gaau3_not_shadowed(p, text, expected):
    assert p.convert(text) == expected


def test_pruning_does_not_change_own_reading_of_pruned_compositional_words(p):
    """Pruned entries are, by construction, only removed when doing so does
    not change their OWN reading — spot-check a sample directly."""
    assert p.convert("香港") == "hoeng1 gong2"
    assert p.convert("教訓") == "gaau3 fan3"
    assert p.convert("正經") == "zing3 ging1"  # genuinely ambiguous, protected from pruning
    assert p.convert("處理") == "cyu5 lei5"    # genuinely ambiguous, protected from pruning


# (input text, expected full jyutping output) — 離合詞 (separable
# verb-object compound) split by a closed-class aspect marker (緊/咗/過/開).
# Fixed in v2.4.0 via data/separable_words.tsv + src/separable.rs: a
# DIFFERENT bug class from the shadowing fixed above — "瞓覺" is never a
# CONTIGUOUS substring once an aspect marker is inserted, so no amount of
# dict pruning could fix it; it needed a whitelist-driven post-segmentation
# pass instead (see CHANGELOG [2.4.0]).
#
# Only 緊 (progressive) and 咗 (perfective) are included here as naturalistic
# gold sentences — 過 (experiential) and 開 (habitual) are grammatically
# supported by the same mechanism (ASPECT_MARKERS in src/separable.rs is the
# genuine closed class of Cantonese aspect markers, kept general for future
# separable-compound entries), but "瞓過覺"/"瞓開覺" read as marked/awkward
# for THIS specific verb-object pair without more context (sleep is a
# routine necessity, not the kind of one-off "experience" 過 usually frames,
# and 開 usually wants a specifying complement like 瞓開呢張床/瞓開晏覺). Native-
# speaker judgment, not a mechanism limitation — see CHANGELOG [2.4.0].
ASPECT_MARKER_GOLD_SENTENCES = [
    ("佢瞓緊覺", "keoi5 fan3 gan2 gaau3"),   # progressive
    ("佢瞓咗覺", "keoi5 fan3 zo2 gaau3"),    # perfective
]


@pytest.mark.parametrize(
    "text,expected",
    ASPECT_MARKER_GOLD_SENTENCES,
    ids=[t for t, _ in ASPECT_MARKER_GOLD_SENTENCES],
)
def test_aspect_marker_insertion_now_resolves_correctly(p, text, expected):
    assert p.convert(text) == expected


def test_unrelated_gok3_usage_not_affected_by_separable_compound_whitelist(p):
    """The whitelist-driven design only fires on the specific verb+noun pair
    in separable_words.tsv (瞓+覺) — it must not over-trigger just because 緊
    or 覺 appear near each other for an unrelated reason."""
    assert p.convert("我覺得好攰") == "ngo5 gok3 dak1 hou2 gui6"
    assert p.convert("我而家好緊張") == "ngo5 ji4 gaa1 hou2 gan2 zoeng1"
