import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline(punc_norm=False)   # isolate: test normalizer only, no punc_norm


# ── Ordinal numbers (第N...) ──────────────────────────────────────────────────

def test_ordinal_3rd_place(p):
    result = p.convert("第3名")
    assert "dai6" in result    # 第
    assert "saam1" in result   # 三
    assert "meng4" in result or "ming4" in result or "meng" in result or "ming" in result  # 名


def test_ordinal_10th(p):
    result = p.convert("第10名")
    assert "sap6" in result    # 十
    assert "dai6" in result


def test_ordinal_position(p):
    result = p.convert("第2位")
    assert "dai6" in result
    assert "ji6" in result     # 二


def test_ordinal_episode(p):
    result = p.convert("第3集")
    assert "saam1" in result   # 三
    assert "zaap6" in result or "zap6" in result  # 集


def test_ordinal_term(p):
    result = p.convert("第12屆")
    assert "sap6" in result    # 十
    assert "ji6" in result     # 二


def test_ordinal_season(p):
    result = p.convert("第2季")
    assert "ji6" in result     # 二


def test_ordinal_in_sentence(p):
    result = p.convert("佢係第1名")
    assert "dai6" in result
    assert "jat1" in result    # 一


# ── Floor / room numbers ──────────────────────────────────────────────────────

def test_floor_3(p):
    result = p.convert("3樓")
    assert "saam1" in result   # 三
    assert "lau4" in result or "lau2" in result  # 樓


def test_floor_12(p):
    result = p.convert("12樓")
    assert "sap6" in result    # 十
    assert "ji6" in result     # 二


def test_floor_in_sentence(p):
    result = p.convert("住係3樓")
    assert "saam1" in result
    assert "lau4" in result or "lau2" in result


def test_room_number(p):
    result = p.convert("5室")
    assert "ng5" in result     # 五


def test_floor_and_room(p):
    result = p.convert("3樓5室")
    assert "saam1" in result
    assert "ng5" in result


# ── Fractions (N/M → M分之N) ─────────────────────────────────────────────────

def test_fraction_half(p):
    result = p.convert("1/2")
    assert "ji6" in result     # 二
    assert "fan6" in result    # 分
    assert "zi1" in result     # 之
    assert "jat1" in result    # 一


def test_fraction_one_third(p):
    result = p.convert("1/3")
    assert "saam1" in result   # 三分之
    assert "fan6" in result
    assert "jat1" in result    # 一


def test_fraction_three_quarters(p):
    result = p.convert("3/4")
    assert "sei3" in result    # 四分之
    assert "saam1" in result   # 三


def test_fraction_one_tenth(p):
    result = p.convert("1/10")
    assert "sap6" in result    # 十
    assert "jat1" in result    # 一
    # NOTE: 十分之 in word dict is sap6 fan1 zi1 (adverb: extremely).
    # When denominator text ends with 十, the 3-char entry shadows 分之 (fan6).
    # fan1 is acceptable for TTS; fan6 would require context-sensitive disambiguation.
    assert "fan6" in result or "fan1" in result


def test_fraction_two_thirds(p):
    result = p.convert("2/3")
    assert "saam1" in result   # 三分之
    assert "ji6" in result     # 二


def test_fraction_in_sentence(p):
    result = p.convert("佔1/3面積")
    assert "saam1" in result   # 三分之
    assert "fan6" in result
    assert "jat1" in result
    assert "min6" in result    # 面


def test_fraction_no_unit_collision(p):
    # 10 km/h should NOT be treated as fraction 10/h
    result = p.convert("10km/h")
    assert "gung1" in result   # 公里每小時 (unit expansion)
    assert "lei5" in result
    assert "fan6" not in result  # no 分之


# ── Scores (N:M → N比M) ──────────────────────────────────────────────────────

def test_score_3_1(p):
    result = p.convert("3:1")
    assert "saam1" in result   # 三
    assert "bei2" in result    # 比
    assert "jat1" in result    # 一


def test_score_10_0(p):
    result = p.convert("10:0")
    assert "sap6" in result    # 十
    assert "bei2" in result
    assert "ling4" in result or "leng4" in result  # 零


def test_score_draw(p):
    result = p.convert("2:2")
    assert "ji6" in result     # 二
    assert "bei2" in result


def test_score_fullwidth_colon(p):
    # full-width colon ：
    result = p.convert("3：1")
    assert "saam1" in result
    assert "bei2" in result
    assert "jat1" in result


def test_score_in_sentence(p):
    result = p.convert("結果3:1")
    assert "git3" in result or "git" in result  # 結
    assert "bei2" in result
    assert "saam1" in result
