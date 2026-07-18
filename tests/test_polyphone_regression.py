"""
Polyphone / 文白異讀 regression suite (v1.7.0).

Gold sentences targeting characters with multiple Jyutping readings where
context (word segmentation) must pick the right one — e.g. 行 (haang4 "walk" /
hang4 "behavior, travel" / hong4 "bank, firm"), 重 (cung4 "repeat" / cung5
"heavy" / zung6 "important"), 平 (peng4 "cheap" / ping4 "flat, peaceful"),
生 (saang1 colloquial / sang1 literary), 坐 (co5 colloquial / zo6 literary),
識 (sik1 colloquial), 近 (gan6 colloquial / kan5 literary), 上 (soeng5 "go up" /
soeng6 "above, previous"), 聽 (ting1 "tomorrow" / teng1 "listen"), 命 (meng6
colloquial / ming6 literary), 正 (zeng3 "great" / zing3 "correct" / zing1
"first month").

Expected values were cross-validated against ToJyutping (CanCLID, BSD-2-Clause,
https://github.com/CanCLID/ToJyutping) — our v1.7.0 build-time data source for
polyphone tie-breaking (see scripts/build_dict.py::load_tojyutping()). This
suite exists to catch regressions in the dict merge priority, NOT to assert
one true Cantonese pronunciation — see CLAUDE.md for the documented v1 scope
(dictionary/word-boundary disambiguation only, no neural context model).
"""
import pytest

from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# (input text, expected full jyutping output)
GOLD_SENTENCES = [
    # 行 — haang4 "walk" / hang4 "behavior, travel" / hong4 "bank, firm, row"
    ("我行路返屋企", "ngo5 haang4 lou6 faan1 uk1 kei2"),
    ("呢個係佢嘅行為", "ni1 go3 hai6 keoi5 ge3 hang4 wai4"),
    ("自由行好方便", "zi6 jau4 hang4 hou2 fong1 bin6"),
    ("銀行幾點開門", "ngan4 hong4 gei2 dim2 hoi1 mun4"),
    ("品行端正", "ban2 hang6 dyun1 zing3"),
    ("行動要快", "hang4 dung6 jiu3 faai3"),
    ("行為不檢", "hang4 wai4 bat1 gim2"),
    ("自由行", "zi6 jau4 hang4"),
    # 重 — cung4 "repeat" / cung5 "heavy" / zung6 "important"
    ("個袋好重", "go3 doi2 hou2 cung5"),
    ("請重複一次", "ceng2 cung4 fuk1 jat1 ci3"),
    ("重要嘅事情", "zung6 jiu3 ge3 si6 cing4"),
    ("體重幾多", "tai2 cung5 gei2 do1"),
    ("重要文件", "zung6 jiu3 man4 gin2"),
    # 平 — peng4 "cheap" / ping4 "flat, peaceful"
    ("呢件衫好平", "ni1 gin6 saam1 hou2 peng4"),
    ("平安夜快樂", "ping4 on1 je6 faai3 lok6"),
    ("和平相處", "wo4 ping4 soeng1 cyu3"),
    # 生 — saang1 colloquial (life/birth) / sang1 literary
    ("生日快樂", "saang1 jat6 faai3 lok6"),
    ("醫生睇病", "ji1 sang1 tai2 beng6"),
    ("出生地點", "ceot1 sang1 dei6 dim2"),
    ("學生讀書", "hok6 saang1 duk6 syu1"),
    ("陌生人", "mak6 sang1 jan4"),
    ("琴日生日", "kam4 jat6 saang1 jat6"),
    ("出生日期", "ceot1 sang1 jat6 kei4"),
    # 坐 — co5 colloquial "sit" / zo6 literary (坐位/坐標)
    ("坐低休息", "co5 dai1 jau1 sik1"),
    ("揾個坐位", "wan2 go3 zo6 wai6"),
    ("坐標系統", "zo6 biu1 hai6 tung2"),
    ("坐位喺邊", "zo6 wai6 hai2 bin1"),
    # 識 — sik1 colloquial "know"
    ("我識佢好耐", "ngo5 sik1 keoi5 hou2 noi6"),
    ("認識新朋友", "jing6 sik1 san1 pang4 jau5"),
    # 近 — gan6 colloquial "near" / kan5 literary (e.g. 遠近)
    ("附近有間餐廳", "fu6 gan6 jau5 gaan1 caan1 teng1"),
    ("近排點呀", "gan6 paai4 dim2 aa4"),
    ("遠近馳名", "jyun5 gan6 ci4 ming4"),
    ("近況如何", "gan6 fong3 jyu4 ho4"),
    # 上 — soeng5 "go up" / soeng6 "above, previous"
    ("上樓梯", "soeng5 lau2 tai1"),
    ("上晝返工", "soeng6 zau3 faan1 gung1"),
    ("上次見面", "soeng6 ci3 gin3 min6"),
    # 聽 — ting1 "tomorrow" (聽日) / teng1 "listen"
    ("聽日見", "ting1 jat6 gin3"),
    ("聽日落雨", "ting1 jat6 lok6 jyu5"),
    ("聽講佢走咗", "teng1 gong2 keoi5 zau2 zo2"),
    # 命 — meng6 colloquial "life/fate" / ming6 literary
    ("好好保重性命", "hou2 hou2 bou2 zung6 sing3 ming6"),
    ("命令佢企定", "ming6 ling6 keoi5 kei5 ding6"),
    ("好命嘅人", "hou2 meng6 ge3 jan4"),
    # 正 — zeng3 "great" / zing3 "correct" / zing1 "first month"
    ("呢個好正", "ni1 go3 hou2 zeng3"),
    ("正常運作", "zing3 soeng4 wan6 zok3"),
    ("正月十五", "zing1 jyut6 sap6 ng5"),
    # 得 — dak1 "can, get"
    ("得閒去街", "dak1 haan4 heoi3 gaai1"),
    ("唔得閒", "m4 dak1 haan4"),
]


@pytest.mark.parametrize("text,expected", GOLD_SENTENCES, ids=[t for t, _ in GOLD_SENTENCES])
def test_polyphone_gold_sentence(p, text, expected):
    assert p.convert(text) == expected


def test_digit_expansion_not_shadowed_by_word_dict():
    """
    Regression guard: adding ToJyutping's word-level entries must not let a
    coincidental multi-char word (e.g. `二六` -> tone-sandhi'd `ji6 luk1`)
    hijack our own digit-by-digit normalizer output, which always expects
    citation tones (CLAUDE.md: "v1 skips tone sandhi").
    """
    p = Pipeline()
    assert "luk6" in p.convert("2026年")
    assert "luk1" not in p.convert("2026年")
    assert p.convert("十六") == "sap6 luk6"
