import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


def test_year_suffix(p):
    result = p.convert("2026年")
    assert "ji6" in result
    assert "ling4" in result
    assert "luk6" in result
    assert "nin4" in result


def test_year_standalone(p):
    result = p.convert("1997")
    assert "jat1" in result
    assert "gau2" in result
    assert "cat1" in result


def test_date_simple(p):
    result = p.convert("6月13日")
    assert "luk6" in result
    assert "jyut6" in result
    assert "sap6" in result
    assert "saam1" in result
    assert "jat6" in result


def test_date_full(p):
    result = p.convert("2026年6月13日")
    assert "ji6" in result
    assert "ling4" in result
    assert "luk6" in result
    assert "nin4" in result
    assert "jyut6" in result
    assert "sap6" in result
    assert "saam1" in result
    assert "jat6" in result


def test_date_dec(p):
    result = p.convert("12月25日")
    assert "sap6" in result
    assert "ji6" in result
    assert "jyut6" in result
    # 25日 → ji6 sap6 ng5 jat6
    assert "ng5" in result
    assert "jat6" in result


def test_percent(p):
    result = p.convert("50%")
    # 百分之 → baak3 fan6 zi1 (分 here is fan6 = "part/fraction", not fan1 "minute")
    assert "baak3" in result
    assert "fan6" in result
    assert "zi1" in result
    assert "ng5" in result
    assert "sap6" in result


def test_phone(p):
    result = p.convert("98765432")
    assert "gau2" in result
    assert "baat3" in result
    assert "cat1" in result
    assert "luk6" in result
    assert "ng5" in result
    assert "sei3" in result
    assert "saam1" in result
    assert "ji6" in result


def test_hkd_currency(p):
    result = p.convert("HK$100")
    # 100 → jat1 baak3, followed by 元 → jyun4
    assert "jat1" in result
    assert "baak3" in result
    assert "jyun4" in result


def test_dollar_currency(p):
    result = p.convert("$50")
    # 50 → ng5 sap6, followed by 元 → jyun4
    assert "ng5" in result
    assert "sap6" in result
    assert "jyun4" in result


def test_currency_postfix_man_4digit(p):
    # 1280 falls inside the 1000-2999 standalone-year heuristic range, but
    # the 蚊 (postfix currency counter) suffix must take priority so this
    # reads as an amount (一千二百八十蚊), not a misread year.
    assert p.convert("1280蚊") == "jat1 cin1 ji6 baak3 baat3 sap6 man1"


def test_currency_postfix_jyun_4digit(p):
    assert p.convert("1500圓") == "jat1 cin1 ng5 baak3 jyun4"


def test_currency_postfix_hou_sin(p):
    assert p.convert("3毫") == "saam1 hou4"
    assert p.convert("5仙") == "ng5 sin1"


def test_bare_4digit_year_heuristic_unaffected(p):
    # No currency/context suffix — the bare-number heuristic (1000-2999 ->
    # digit-by-digit, else cardinal) is unchanged by the currency fix.
    assert p.convert("2723") == "ji6 cat1 ji6 saam1"
    assert p.convert("4567") == "sei3 cin1 ng5 baak3 luk6 sap6 cat1"


def test_time(p):
    result = p.convert("下午3時15分")
    assert "saam1" in result
    assert "si4" in result
    assert "sap6" in result
    assert "ng5" in result
    assert "fan1" in result


def test_cardinal_in_context(p):
    result = p.convert("有3個人")
    assert "jau5" in result
    assert "saam1" in result
    assert "go3" in result
    assert "jan4" in result


def test_fullwidth_digits(p):
    result = p.convert("２０２６年")
    assert "ji6" in result
    assert "ling4" in result
    assert "luk6" in result
    assert "nin4" in result


def test_mixed_date_in_sentence(p):
    result = p.convert("今日係2026年6月13日")
    assert "gam1" in result
    assert "jat6" in result
    assert "hai6" in result
    assert "ji6" in result
    assert "ling4" in result
    assert "luk6" in result
    assert "nin4" in result
    assert "jyut6" in result
    assert "sap6" in result
    assert "saam1" in result


# ── v1.2: decimal numbers ─────────────────────────────────────────────────────

def test_decimal_plain(p):
    result = p.convert("3.14")
    assert "saam1" in result   # 三
    assert "dim2" in result or "jat6" in result  # 點一四 (點 → dim2)


def test_decimal_percent(p):
    result = p.convert("50.5%")
    assert "baak3" in result   # 百
    assert "fan6" in result    # 分
    assert "zi1" in result     # 之
    assert "ng5" in result     # 五
    assert "sap6" in result    # 十


# ── v1.2: measurement units ───────────────────────────────────────────────────

def test_unit_kmh(p):
    result = p.convert("速度係120km/h")
    assert "jat1" in result    # 一百
    assert "baak3" in result
    assert "ji6" in result     # 二十
    assert "sap6" in result
    assert "gung1" in result   # 公里每小時
    assert "lei5" in result
    assert "mui5" in result
    assert "siu2" in result or "siu6" in result  # 小時


def test_unit_celsius(p):
    result = p.convert("氣溫36.5°C")
    assert "saam1" in result   # 三十六 → 三
    assert "luk6" in result    # 六
    assert "sip3" in result or "syut3" in result or "sip" in result  # 攝氏
    assert "dou6" in result    # 度


def test_unit_celsius_simple(p):
    # 36°C (integer)
    result = p.convert("36°C")
    assert "saam1" in result
    assert "luk6" in result


def test_unit_kg(p):
    result = p.convert("重量係75kg")
    assert "cat1" in result    # 七十五
    assert "sap6" in result
    assert "ng5" in result
    assert "gung1" in result   # 公斤
    assert "gan1" in result


def test_unit_km(p):
    result = p.convert("100km")
    assert "jat1" in result
    assert "baak3" in result
    assert "gung1" in result   # 公
    assert "lei5" in result    # 里


def test_unit_ml(p):
    result = p.convert("250ml")
    assert "ji6" in result or "leung5" in result   # 二百五十
    assert "baak3" in result
    assert "hou4" in result    # 毫
    assert "sing1" in result   # 升


def test_unit_m2(p):
    result = p.convert("3m²")
    assert "saam1" in result   # 三
    assert "ping4" in result   # 平
    assert "fong1" in result   # 方
    assert "mai5" in result    # 米


def test_unit_space_before(p):
    # optional space between number and unit
    result = p.convert("120 km/h")
    assert "gung1" in result
    assert "lei5" in result


# ── v1.2: currency ────────────────────────────────────────────────────────────

def test_currency_usd(p):
    result = p.convert("USD100")
    assert "jat1" in result
    assert "baak3" in result
    assert "mei5" in result    # 美
    assert "jyun4" in result   # 元


def test_currency_eur(p):
    result = p.convert("EUR200")
    assert "ji6" in result
    assert "baak3" in result
    assert "au1" in result or "ngau1" in result or "au" in result  # 歐


def test_currency_yen_symbol(p):
    result = p.convert("¥500")
    assert "ng5" in result
    assert "baak3" in result
    assert "jat6" in result    # 日
    assert "jyun4" in result   # 圓


def test_currency_rmb_symbol(p):
    result = p.convert("￥200")
    assert "ji6" in result
    assert "baak3" in result
    assert "jan4" in result    # 人
    assert "man4" in result    # 民


def test_currency_gbp_symbol(p):
    result = p.convert("£80")
    assert "baat3" in result
    assert "sap6" in result
    assert "jing1" in result   # 英
    assert "bong2" in result   # 鎊


def test_currency_usd_space(p):
    # USD with space before digits
    result = p.convert("USD 100")
    assert "mei5" in result
    assert "jyun4" in result
