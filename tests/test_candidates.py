"""
v1.9.0 — Pipeline.convert_candidates() tests (Phase 7b-2, Candidates API).

convert_candidates() surfaces every known alternate reading for a polyphone
(多音字) as a rank-ordered list (most-likely first), instead of committing to
a single reading like convert()/convert_detailed() do. Ambiguity is only
reported where the bundled data actually has 2+ known readings for that exact
token (or, for an out-of-vocabulary single character, that character).

Run from repo root:  pytest tests/ -v
"""
import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# ── Word-level ambiguity ─────────────────────────────────────────────────────

def test_word_level_ambiguity_reports_multiple_candidates(p):
    result = p.convert_candidates("正經")
    assert result == [("正經", ["zing3 ging1", "zing1 ging1"], "yue")]


def test_word_level_candidates_first_entry_matches_convert(p):
    # The rank-0 candidate must be exactly what convert() commits to.
    candidates = p.convert_candidates("處理")
    assert candidates[0][1][0] == p.convert("處理")
    assert len(candidates[0][1]) >= 2


# ── Single-char (OOV fallback) ambiguity ────────────────────────────────────

def test_single_char_ambiguity_reports_multiple_candidates(p):
    result = p.convert_candidates("行")
    token, cands, lang = result[0]
    assert token == "行"
    assert lang == "yue"
    assert cands[0] == "haang4"  # matches convert()'s committed reading
    assert len(cands) >= 2
    assert cands[0] == p.convert("行")


def test_single_char_candidates_dedup_and_order():
    # A different bundled-in char with known alternates.
    p = Pipeline()
    cands = p.convert_candidates("重")[0][1]
    assert cands[0] == p.convert("重")
    assert len(set(cands)) == len(cands)  # no duplicate readings


# ── No known ambiguity → single-item list ───────────────────────────────────

def test_no_ambiguity_reports_single_candidate(p):
    assert p.convert_candidates("香港") == [("香港", ["hoeng1 gong2"], "yue")]


def test_word_dict_hit_with_no_alternates_is_single_item(p):
    # "行為" is an exact word_dict entry with no word-level candidates row,
    # even though its first character "行" is itself ambiguous alone.
    assert p.convert_candidates("行為") == [("行為", ["hang4 wai4"], "yue")]


def test_unknown_char_reports_single_item_unihan_reading(p):
    result = p.convert_candidates("龘")
    assert result == [("龘", ["daap6"], "yue")]


# ── English / punctuation passthrough ────────────────────────────────────────

def test_english_and_punctuation_single_item_each(p):
    result = p.convert_candidates("hi!")
    assert result == [
        ("hi", ["hi"], "en"),
        ("!", ["!"], "punct"),
    ]


def test_mixed_text_candidates(p):
    result = p.convert_candidates("你好嘅 hi")
    tokens = [tok for tok, _, _ in result]
    assert tokens == ["你", "好", "嘅", "hi"]
    langs = [lang for _, _, lang in result]
    assert langs == ["yue", "yue", "yue", "en"]
    # "你" and "好" both have known char-level ambiguity in the bundled data.
    you_cands = result[0][1]
    assert you_cands[0] == "nei5"
    assert len(you_cands) >= 2


# ── user_dict interaction ────────────────────────────────────────────────────

def test_user_dict_override_collapses_ambiguity_to_single_candidate():
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    assert p.convert_candidates("正經") == [("正經", ["zing1 ging1"], "yue")]


def test_user_dict_override_on_ambiguous_char_collapses_too():
    p = Pipeline(user_dict={"行": "hong4"})
    assert p.convert_candidates("行") == [("行", ["hong4"], "yue")]


def test_no_user_dict_still_shows_full_ambiguity(p):
    assert len(p.convert_candidates("正經")[0][1]) == 2


# ── Empty input ──────────────────────────────────────────────────────────────

def test_empty_text_returns_empty_list(p):
    assert p.convert_candidates("") == []


# ── Consistency with convert_detailed() ─────────────────────────────────────

def test_tokens_and_langs_match_convert_detailed(p):
    text = "你好嘅，I love Hong Kong"
    detailed = p.convert_detailed(text)
    candidates = p.convert_candidates(text)
    assert [tok for tok, _, _ in detailed] == [tok for tok, _, _ in candidates]
    assert [lang for _, _, lang in detailed] == [lang for _, _, lang in candidates]
    # The committed reading must always be the rank-0 candidate.
    for (_, jp, _), (_, cands, _) in zip(detailed, candidates):
        assert cands[0] == jp
