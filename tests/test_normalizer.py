import pytest
from canto_g2p import Pipeline


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
