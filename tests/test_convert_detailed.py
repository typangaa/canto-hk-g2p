import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# ── Return-type guarantees ───────────────────────────────────────────────────

def test_empty_string_returns_empty_list(p):
    assert p.convert_detailed("") == []


def test_result_is_list(p):
    r = p.convert_detailed("香港")
    assert isinstance(r, list)


def test_each_element_is_3_tuple(p):
    r = p.convert_detailed("香港")
    for item in r:
        assert isinstance(item, tuple)
        assert len(item) == 3


def test_all_fields_are_str(p):
    r = p.convert_detailed("你好，hello")
    for token, jp, lang in r:
        assert isinstance(token, str)
        assert isinstance(jp, str)
        assert isinstance(lang, str)


def test_lang_values_are_valid(p):
    # every lang tag must be one of the three defined values
    valid = {"yue", "en", "punct"}
    r = p.convert_detailed("你好，hello 123")
    for _, _, lang in r:
        assert lang in valid


# ── Pure Cantonese ────────────────────────────────────────────────────────────

def test_pure_cantonese_hongkong(p):
    r = p.convert_detailed("香港")
    assert len(r) == 1
    token, jp, lang = r[0]
    assert token == "香港"
    assert jp == "hoeng1 gong2"
    assert lang == "yue"


def test_pure_cantonese_particle_ge3(p):
    r = p.convert_detailed("嘅")
    assert len(r) == 1
    _, jp, lang = r[0]
    assert jp == "ge3"
    assert lang == "yue"


def test_pure_cantonese_negation(p):
    r = p.convert_detailed("唔")
    assert len(r) == 1
    _, jp, lang = r[0]
    assert jp == "m4"
    assert lang == "yue"


# ── English passthrough ───────────────────────────────────────────────────────

def test_english_passthrough_hello(p):
    # Latin tokens pass through unchanged — dict is never consulted for non-CJK
    r = p.convert_detailed("hello")
    assert len(r) == 1
    token, jp, lang = r[0]
    assert token == "hello"
    assert jp == "hello"
    assert lang == "en"


def test_pure_english_phrase_lang_tags(p):
    # All tokens in a pure English phrase should be "en" or "punct"
    r = p.convert_detailed("I love Hong Kong")
    for _, _, lang in r:
        assert lang in ("en", "punct")


# ── Punctuation ───────────────────────────────────────────────────────────────

def test_punctuation_token_present(p):
    r = p.convert_detailed("你好，")
    langs = [lang for _, _, lang in r]
    assert "punct" in langs


def test_punctuation_token_value(p):
    r = p.convert_detailed("你好，")
    punct_tokens = [tok for tok, _, lang in r if lang == "punct"]
    assert "，" in punct_tokens


def test_cantonese_tokens_before_punct(p):
    r = p.convert_detailed("你好，")
    yue_jps = [jp for _, jp, lang in r if lang == "yue"]
    # 你好 → nei5 hou2 (one or two tokens depending on segmentation)
    combined = " ".join(yue_jps)
    assert "nei5" in combined
    assert "hou2" in combined


# ── Mixed code-switching ──────────────────────────────────────────────────────

def test_code_switch_three_tokens(p):
    # 佢send咗 — at minimum three language-distinct spans
    r = p.convert_detailed("佢send咗")
    tokens_by_lang = {lang: tok for tok, _, lang in r}
    # must contain at least one yue token
    yue_jps = [jp for _, jp, lang in r if lang == "yue"]
    combined_yue = " ".join(yue_jps)
    assert "keoi5" in combined_yue  # 佢
    assert "zo2" in combined_yue    # 咗


def test_code_switch_send_is_en(p):
    r = p.convert_detailed("佢send咗")
    en_tokens = [tok for tok, _, lang in r if lang == "en"]
    assert "send" in en_tokens


def test_code_switch_send_lang(p):
    r = p.convert_detailed("佢send咗")
    for tok, _, lang in r:
        if tok == "send":
            assert lang == "en"
            break
    else:
        pytest.fail("'send' token not found in convert_detailed output")


def test_code_switch_longer(p):
    r = p.convert_detailed("佢send咗email俾我")
    all_jp = " ".join(jp for _, jp, _ in r)
    assert "keoi5" in all_jp   # 佢
    assert "zo2" in all_jp     # 咗
    assert "bei2" in all_jp    # 俾
    assert "ngo5" in all_jp    # 我


# ── Jyutping consistency with convert() ──────────────────────────────────────

def test_join_matches_convert_hongkong(p):
    text = "香港"
    detail = p.convert_detailed(text)
    joined = " ".join(jp for _, jp, _ in detail)
    assert joined == p.convert(text)


def test_join_matches_convert_ge3(p):
    text = "嘅"
    detail = p.convert_detailed(text)
    joined = " ".join(jp for _, jp, _ in detail)
    assert joined == p.convert(text)


def test_join_matches_convert_mixed(p):
    text = "你好嘅"
    detail = p.convert_detailed(text)
    joined = " ".join(jp for _, jp, _ in detail)
    assert joined == p.convert(text)


# ── Number expansion ──────────────────────────────────────────────────────────

def test_number_expansion_2026_year(p):
    # Normalizer expands "2026年" → "二零二六年" before segmentation,
    # so all tokens should be lang="yue"
    r = p.convert_detailed("2026年")
    for _, _, lang in r:
        assert lang == "yue"


def test_number_expansion_2026_year_syllables(p):
    r = p.convert_detailed("2026年")
    all_jp = " ".join(jp for _, jp, _ in r)
    assert "ji6" in all_jp     # 二
    assert "ling4" in all_jp   # 零
    assert "luk6" in all_jp    # 六
    assert "nin4" in all_jp    # 年


def test_number_expansion_join_matches_convert(p):
    text = "2026年"
    detail = p.convert_detailed(text)
    joined = " ".join(jp for _, jp, _ in detail)
    assert joined == p.convert(text)


# ── Batch consistency ─────────────────────────────────────────────────────────

def test_batch_consistency_hongkong(p):
    text = "香港"
    detail_jp = " ".join(jp for _, jp, _ in p.convert_detailed(text))
    assert detail_jp == p.convert(text)


def test_batch_consistency_hei3_haa1(p):
    text = "佢好"
    detail_jp = " ".join(jp for _, jp, _ in p.convert_detailed(text))
    assert detail_jp == p.convert(text)


def test_detailed_is_reusable(p):
    # Same pipeline instance produces identical results on repeated calls
    r1 = p.convert_detailed("香港")
    r2 = p.convert_detailed("香港")
    assert r1 == r2
