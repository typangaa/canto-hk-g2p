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


# ── Batch (v1.10.0) ──────────────────────────────────────────────────────────

def test_batch_matches_per_text_calls(p):
    texts = ["正經", "香港銀行", "hi! bye"]
    batch_result = p.convert_candidates_batch(texts)
    per_text_result = [p.convert_candidates(t) for t in texts]
    assert batch_result == per_text_result


def test_batch_preserves_order_and_length(p):
    texts = ["行", "重", "處理", "香港"]
    result = p.convert_candidates_batch(texts)
    assert len(result) == len(texts)
    # each sublist's first token must be the first token of that same text
    # in isolation — confirms batch didn't shuffle/cross-mix inputs.
    for text, sublist in zip(texts, result):
        assert sublist[0][0] == p.convert_candidates(text)[0][0]


def test_batch_empty_list_returns_empty_list(p):
    assert p.convert_candidates_batch([]) == []


def test_batch_empty_string_element_returns_empty_sublist(p):
    result = p.convert_candidates_batch(["正經", ""])
    assert result[0] == p.convert_candidates("正經")
    assert result[1] == []


# ── Scored (v1.11.0, issue #12) ──────────────────────────────────────────────

def test_scored_word_level_tied(p):
    # "正經" isn't an exact ToJyutping trie node, so it falls back to
    # rime-cantonese's raw arbitrary tie-break -> "tied".
    result = p.convert_candidates_scored("正經")
    assert result == [("正經", ["zing3 ging1", "zing1 ging1"], "yue", "tied")]


def test_scored_char_level_ranked(p):
    # Single chars are covered directly by ToJyutping's own trie -> "ranked".
    result = p.convert_candidates_scored("行")
    token, cands, lang, confidence = result[0]
    assert token == "行"
    assert lang == "yue"
    assert confidence == "ranked"
    assert cands[0] == p.convert("行")
    assert len(cands) >= 2


def test_scored_no_ambiguity_is_certain(p):
    assert p.convert_candidates_scored("香港") == [
        ("香港", ["hoeng1 gong2"], "yue", "certain")
    ]


def test_scored_english_and_punct_certain(p):
    result = p.convert_candidates_scored("hi!")
    assert result == [
        ("hi", ["hi"], "en", "certain"),
        ("!", ["!"], "punct", "certain"),
    ]


def test_scored_user_dict_override_is_certain():
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    assert p.convert_candidates_scored("正經") == [
        ("正經", ["zing1 ging1"], "yue", "certain")
    ]


def test_scored_confidence_only_present_when_ambiguous(p):
    # Rank-0 candidate must always match convert()'s committed reading,
    # regardless of confidence tier.
    for text in ["正經", "行", "香港"]:
        scored = p.convert_candidates_scored(text)
        assert scored[0][1][0] == p.convert(text)


def test_scored_empty_text_returns_empty_list(p):
    assert p.convert_candidates_scored("") == []


def test_scored_tokens_and_candidates_match_convert_candidates(p):
    text = "你好嘅，I love Hong Kong"
    candidates = p.convert_candidates(text)
    scored = p.convert_candidates_scored(text)
    assert [tok for tok, _, _ in candidates] == [tok for tok, _, _, _ in scored]
    assert [c for _, c, _ in candidates] == [c for _, c, _, _ in scored]
    assert [lang for _, _, lang in candidates] == [lang for _, _, lang, _ in scored]
    for confidence in [conf for *_, conf in scored]:
        assert confidence in {"certain", "ranked", "tied"}


# ── Scored batch (v1.11.0) ───────────────────────────────────────────────────

def test_scored_batch_matches_per_text_calls(p):
    texts = ["正經", "香港銀行", "hi! bye"]
    batch_result = p.convert_candidates_scored_batch(texts)
    per_text_result = [p.convert_candidates_scored(t) for t in texts]
    assert batch_result == per_text_result


def test_scored_batch_preserves_order_and_length(p):
    texts = ["行", "重", "處理", "香港"]
    result = p.convert_candidates_scored_batch(texts)
    assert len(result) == len(texts)
    for text, sublist in zip(texts, result):
        assert sublist[0][0] == p.convert_candidates_scored(text)[0][0]


def test_scored_batch_empty_list_returns_empty_list(p):
    assert p.convert_candidates_scored_batch([]) == []


def test_scored_batch_empty_string_element_returns_empty_sublist(p):
    result = p.convert_candidates_scored_batch(["正經", ""])
    assert result[0] == p.convert_candidates_scored("正經")
    assert result[1] == []
