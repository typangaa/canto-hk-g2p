"""
v2.0.0 — Pipeline.convert_candidates() tests (consolidated Candidates API).

convert_candidates() surfaces every known alternate reading for a polyphone
(多音字) as a rank-ordered list (most-likely first), instead of committing to
a single reading like convert()/convert_detailed() do. Ambiguity is only
reported where the bundled data actually has 2+ known readings for that
exact token (or, for an out-of-vocabulary single character, that character).

Since v2.0.0, each result also carries a categorical `confidence` tag
("certain" / "ranked" / "tied" — issue #12) and a `source` tag naming which
data layer produced the rank-0 reading ("rime" / "tojyutping" /
"tojyutping_tiebreak" / "oral_hk" / "variant_alias" / "hkcancor_verified" /
"unihan" / "user_dict" / "passthrough" / "char_fallback" / "unresolved" /
"unknown" — issue #13). No numeric probability is exposed by design — see
CHANGELOG for the research behind this categorical-only design.

`"variant_alias"` (v2.1.0) is a distinct source from `"oral_hk"`: it marks a
借音字 (phonetic-loan miswriting, e.g. 訓覺 for 瞓覺) resolved by copying the
correctly-spelled canonical word's reading — see data/variant_words.tsv.

`"hkcancor_verified"` (v2.2.0) marks a 變調 (changed-tone) word-level
override: the word's real spoken tone (found by diffing HKCanCor's
transcribed corpus against citation-tone output, then confirmed by a native
speaker) differs from what the citation-tone character fallback would
produce — see data/tone_sandhi_words.tsv.

Run from repo root:  pytest tests/ -v
"""
import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


VALID_CONFIDENCE = {"certain", "ranked", "tied"}
VALID_SOURCE = {
    "rime", "tojyutping", "tojyutping_tiebreak", "oral_hk", "variant_alias",
    "hkcancor_verified", "unihan", "user_dict", "passthrough", "char_fallback",
    "unresolved", "unknown",
}


# ── Word-level ambiguity ─────────────────────────────────────────────────────

def test_word_level_ambiguity_reports_multiple_candidates(p):
    result = p.convert_candidates("正經")
    token, cands, lang, confidence, source = result[0]
    assert token == "正經"
    assert cands == ["zing3 ging1", "zing1 ging1"]
    assert lang == "yue"
    assert confidence in VALID_CONFIDENCE
    assert source in VALID_SOURCE


def test_word_level_candidates_first_entry_matches_convert(p):
    # The rank-0 candidate must be exactly what convert() commits to.
    candidates = p.convert_candidates("處理")
    assert candidates[0][1][0] == p.convert("處理")
    assert len(candidates[0][1]) >= 2


# ── Single-char (OOV fallback) ambiguity ────────────────────────────────────

def test_single_char_ambiguity_reports_multiple_candidates(p):
    result = p.convert_candidates("行")
    token, cands, lang, confidence, source = result[0]
    assert token == "行"
    assert lang == "yue"
    assert cands[0] == "haang4"  # matches convert()'s committed reading
    assert len(cands) >= 2
    assert cands[0] == p.convert("行")
    assert confidence in VALID_CONFIDENCE
    assert source in VALID_SOURCE


def test_single_char_candidates_dedup_and_order():
    # A different bundled-in char with known alternates.
    p = Pipeline()
    cands = p.convert_candidates("重")[0][1]
    assert cands[0] == p.convert("重")
    assert len(set(cands)) == len(cands)  # no duplicate readings


# ── No known ambiguity → single-item list, "certain" confidence ────────────

def test_no_ambiguity_reports_single_candidate(p):
    result = p.convert_candidates("香港")
    assert result == [("香港", ["hoeng1 gong2"], "yue", "certain", "rime")]


def test_word_dict_hit_with_no_alternates_is_single_item(p):
    # "行為" is an exact word_dict entry with no word-level candidates row,
    # even though its first character "行" is itself ambiguous alone.
    result = p.convert_candidates("行為")
    assert result[0][:3] == ("行為", ["hang4 wai4"], "yue")
    assert result[0][3] == "certain"


def test_unknown_char_reports_single_item_unihan_reading(p):
    result = p.convert_candidates("龘")
    token, cands, lang, confidence, source = result[0]
    assert (token, cands, lang) == ("龘", ["daap6"], "yue")
    assert confidence == "certain"


# ── English / punctuation passthrough ────────────────────────────────────────

def test_english_and_punctuation_single_item_each(p):
    result = p.convert_candidates("hi!")
    assert result == [
        ("hi", ["hi"], "en", "certain", "passthrough"),
        ("!", ["!"], "punct", "certain", "passthrough"),
    ]


def test_mixed_text_candidates(p):
    result = p.convert_candidates("你好嘅 hi")
    tokens = [tok for tok, _, _, _, _ in result]
    assert tokens == ["你", "好", "嘅", "hi"]
    langs = [lang for _, _, lang, _, _ in result]
    assert langs == ["yue", "yue", "yue", "en"]
    # "你" and "好" both have known char-level ambiguity in the bundled data.
    you_cands = result[0][1]
    assert you_cands[0] == "nei5"
    assert len(you_cands) >= 2


# ── user_dict interaction ────────────────────────────────────────────────────

def test_user_dict_override_collapses_ambiguity_to_single_candidate():
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    result = p.convert_candidates("正經")
    assert result == [("正經", ["zing1 ging1"], "yue", "certain", "user_dict")]


def test_user_dict_override_on_ambiguous_char_collapses_too():
    p = Pipeline(user_dict={"行": "hong4"})
    result = p.convert_candidates("行")
    assert result == [("行", ["hong4"], "yue", "certain", "user_dict")]


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
    assert [tok for tok, *_ in detailed] == [tok for tok, *_ in candidates]
    assert [row[2] for row in detailed] == [row[2] for row in candidates]
    # The committed reading must always be the rank-0 candidate, and
    # confidence/source must match exactly between the two methods.
    for (_, jp, _, det_conf, det_src), (_, cands, _, cand_conf, cand_src) in zip(
        detailed, candidates
    ):
        assert cands[0] == jp
        assert det_conf == cand_conf
        assert det_src == cand_src


# ── Confidence tag (issue #12) ───────────────────────────────────────────────

def test_confidence_values_are_valid(p):
    result = p.convert_candidates("你好嘅，I love Hong Kong 正經 行 處理")
    for _, _, _, confidence, _ in result:
        assert confidence in VALID_CONFIDENCE


def test_word_level_tied_confidence(p):
    # "正經" isn't an exact ToJyutping trie node, so it falls back to
    # rime-cantonese's raw arbitrary tie-break.
    result = p.convert_candidates("正經")
    assert result[0][3] == "tied"


def test_unambiguous_token_is_certain(p):
    assert p.convert_candidates("香港")[0][3] == "certain"


# ── Source tag (issue #13) ───────────────────────────────────────────────────

def test_source_values_are_valid(p):
    result = p.convert_candidates("你好嘅，I love Hong Kong 正經 行 處理")
    for _, _, _, _, source in result:
        assert source in VALID_SOURCE


def test_source_passthrough_for_non_cjk(p):
    result = p.convert_candidates("hi!")
    assert result[0][4] == "passthrough"
    assert result[1][4] == "passthrough"


def test_source_user_dict_for_override():
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    assert p.convert_candidates("正經")[0][4] == "user_dict"


def test_source_rime_for_plain_dict_hit(p):
    assert p.convert_candidates("香港")[0][4] == "rime"


def test_source_variant_alias_for_phonetic_loan_word(p):
    """訓覺 is a 借音字 miswriting of 瞓覺 (data/variant_words.tsv, v2.1.0)."""
    result = p.convert_candidates("訓覺")
    assert result[0][1] == ["fan3 gaau3"]
    assert result[0][3] == "certain"
    assert result[0][4] == "variant_alias"


def test_variant_alias_does_not_corrupt_native_reading(p):
    """訓 keeps its own genuine reading (fan3) in 教訓/訓練 — only the exact
    借音字 word 訓覺 is affected, not the character 訓 in general."""
    assert p.convert_candidates("教訓")[0][4] == "rime"
    assert p.convert_candidates("訓練")[0][4] == "rime"


def test_variant_alias_gan2_hai6_becomes_gang2_hai6(p):
    """緊係 is a common miswriting of 梗係 ("of course")."""
    assert p.convert("緊係") == "gang2 hai6"
    assert p.convert_candidates("緊係")[0][4] == "variant_alias"
    # 緊 keeps its own reading (gan2) in genuine words — 緊要/要緊 unaffected.
    assert p.convert("緊要") == "gan2 jiu3"
    assert p.convert("要緊") == "jiu3 gan2"


@pytest.mark.parametrize("variant,canonical,expected", [
    ("係度", "喺度", "hai2 dou6"),
    ("念住", "諗住", "nam2 zyu6"),
    ("林住", "諗住", "nam2 zyu6"),
    ("禁掣", "撳掣", "gam6 zai3"),
    ("㩒掣", "撳掣", "gam6 zai3"),
    ("令女", "靚女", "leng3 neoi2"),
    ("亂嗡", "亂噏", "lyun2 ap1"),
    ("晒氣", "嘥氣", "saai1 hei3"),
    ("甘樣", "噉樣", "gam2 joeng2"),
    ("甘多", "咁多", "gam3 do1"),
    ("吾該", "唔該", "m4 goi1"),
    ("吾知", "唔知", "m4 zi1"),
    ("吾好", "唔好", "m4 hou2"),
])
def test_variant_alias_expanded_seed_list(p, variant, canonical, expected):
    """v2.1.0 expansion — corroborated by multiple independent research
    passes, each verified individually against the pipeline (several
    similarly-plausible candidates from the same research were rejected:
    e.g. 個度→嗰度 for a real segmentation collision with 度數, and 既→嘅/
    黎→嚟-style disputed-reading pairs)."""
    assert p.convert(variant) == expected
    assert p.convert(canonical) == expected
    assert p.convert_candidates(variant)[0][4] == "variant_alias"


def test_variant_alias_no_segmentation_collision_with_longer_words(p):
    """個度 (for 嗰度) was considered and rejected: it would shadow 度數
    inside 個度數 ("this reading/number") via longest-match segmentation.
    Regression guard — 個度數 must keep splitting as 個 + 度數."""
    assert p.convert("個度數") == "go3 dou6 sou3"
    assert p.convert("支吾其詞") == "zi1 ng4 kei4 ci4"


@pytest.mark.parametrize("word,expected", [
    ("今年", "gam1 nin2"),
    ("紅籌", "hung4 cau2"),
    ("藍籌", "laam4 cau2"),
    ("新聞", "san1 man2"),
    ("無喇喇", "mou4 laa1 laa1"),
    ("之類", "zi1 leoi2"),
])
def test_hkcancor_verified_tone_sandhi_words(p, word, expected):
    """v2.2.0 — HKCanCor-verified 變調 (changed-tone) word corrections
    (data/tone_sandhi_words.tsv). Found by diffing HKCanCor's transcribed
    corpus against citation-tone output; 新聞/之類 were also rime-cantonese
    ties that the ToJyutping tie-break had resolved to the wrong side."""
    assert p.convert(word) == expected
    result = p.convert_candidates(word)[0]
    assert result[3] == "certain"
    assert result[4] == "hkcancor_verified"


def test_hkcancor_verified_does_not_corrupt_native_reading(p):
    """The characters behind the tone_sandhi_words entries keep their own
    citation reading in unrelated compounds — these are word-level overrides,
    never char-level."""
    assert p.convert("年尾") == "nin4 mei5"
    assert p.convert("聞名") == "man4 ming4"
    assert p.convert("種類") == "zung2 leoi6"
    assert p.convert("籌備") == "cau4 bei6"
    assert p.convert("喇叭") == "laa3 baa1"


# ── Batch ─────────────────────────────────────────────────────────────────

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
