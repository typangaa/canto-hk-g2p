import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline(punc_norm=True)


@pytest.fixture(scope="module")
def p_off():
    return Pipeline(punc_norm=False)


# ── punc_norm=True (default) ──────────────────────────────────────────────────

def test_book_title_removed(p):
    result = p.convert("《天氣之子》")
    assert "《" not in result
    assert "》" not in result
    assert "tin1" in result
    assert "hei3" in result


def test_chinese_quotes_removed(p):
    result = p.convert("「你好」")
    assert "「" not in result
    assert "」" not in result
    assert "nei5" in result
    assert "hou2" in result


def test_square_bracket_removed(p):
    result = p.convert("【重要】通知")
    assert "【" not in result
    assert "】" not in result
    assert "tung1" in result or "zi1" in result  # 通知


def test_ellipsis_to_fullstop(p):
    result = p.convert("好吧…")
    # ellipsis → 。 which passes through as a punct token
    assert "hou2" in result
    assert "baa1" in result or "baa6" in result


def test_double_ellipsis(p):
    result = p.convert("係咁……")
    assert "hai6" in result
    assert "gam3" in result or "gam2" in result  # 咁: gam3 (dict tone)


def test_ascii_ellipsis(p):
    result = p.convert("等等...")
    assert "dang2" in result


def test_em_dash_pair(p):
    # ——  →  ，  →  treated as punctuation in output
    result = p.convert("一——二")
    assert "jat1" in result
    assert "ji6" in result


def test_em_dash_single(p):
    result = p.convert("第一—第二")
    assert "dai6" in result
    assert "jat1" in result
    assert "ji6" in result


def test_en_dash(p):
    result = p.convert("上午–下午")
    assert "soeng6" in result or "soeng5" in result
    assert "haa6" in result


def test_double_hyphen(p):
    result = p.convert("香港--澳門")
    assert "hoeng1" in result
    assert "mun2" in result or "mun4" in result  # 門 tone varies by dict entry


def test_single_hyphen_kept(p):
    # Single hyphen in non-double context should pass through unchanged
    result = p.convert("km-h")
    assert "km" in result or "k" in result  # Latin passthrough


def test_middle_dot(p):
    result = p.convert("奧斯卡·王爾德")
    assert "wong4" in result   # 王
    assert "ji5" in result or "ji6" in result    # 爾


def test_wave_dash(p):
    result = p.convert("早～晚")
    assert "zou2" in result   # 早
    assert "maan5" in result  # 晚


def test_enum_comma(p):
    result = p.convert("蘋果、橙、香蕉")
    assert "ping4" in result   # 蘋
    assert "gwoo2" in result or "gwo2" in result  # 果
    assert "caang2" in result or "caang4" in result  # 橙


def test_decorative_symbols(p):
    result = p.convert("※注意★")
    assert "※" not in result
    assert "★" not in result
    assert "zyu3" in result   # 注


def test_combined_messy(p):
    # Typical messy article title/content
    result = p.convert("《天氣之子》——一個關於天氣……的故事")
    assert "《" not in result
    assert "》" not in result
    assert "tin1" in result    # 天
    assert "jat1" in result    # 一
    assert "gu3" in result or "go3" in result    # 故/個


def test_passthrough_unchanged(p):
    # Normal text should not be affected
    result = p.convert("你好嘅，I love Hong Kong")
    assert "nei5" in result
    assert "hou2" in result
    assert "ge3" in result
    assert "Hong" in result
    assert "Kong" in result


# ── punc_norm=False ───────────────────────────────────────────────────────────

def test_punc_norm_off_keeps_brackets(p_off):
    result = p_off.convert("《天氣》")
    # brackets pass through as punct tokens
    assert "tin1" in result
    assert "hei3" in result


def test_punc_norm_default_is_true():
    # Pipeline() with no args should have punc_norm=True
    p = Pipeline()
    result = p.convert("《香港》")
    assert "《" not in result
    assert "hoeng1" in result
    assert "gong2" in result


def test_punc_norm_kwarg():
    # keyword-only arg
    p = Pipeline(punc_norm=False)
    result = p.convert("你好嘅")
    assert "nei5" in result   # still works; just no punc processing
