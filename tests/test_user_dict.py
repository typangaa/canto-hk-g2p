"""
v1.8.0 — Pipeline(user_dict=...) runtime override tests.

user_dict is a runtime override dictionary (word/char -> jyutping) layered
on top of every bundled dictionary at the highest priority. It also
participates in segmentation, so a multi-char override is never silently
split apart before lookup.

Run from repo root:  pytest tests/ -v
"""
import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# ── Override behavior ────────────────────────────────────────────────────────

def test_override_changes_known_tied_reading():
    # Baseline (v1.7.1 tie-break pick) is "zing3 ging1"; force the other one.
    baseline = Pipeline().convert("正經")
    assert baseline == "zing3 ging1"

    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    assert p.convert("正經") == "zing1 ging1"


def test_override_word_not_in_any_bundled_dict():
    p = Pipeline(user_dict={"老世": "lou5 sai3"})
    assert p.convert("老世") == "lou5 sai3"


def test_override_single_char():
    baseline = Pipeline().convert("行")
    p = Pipeline(user_dict={"行": "hong4"})
    result = p.convert("行")
    assert result == "hong4"
    # Sanity: the override actually changed something, or at minimum is
    # deterministic and consistent — don't assert baseline != result since
    # rime's default single-char reading for 行 may already be hong4.
    assert isinstance(baseline, str)


def test_override_does_not_affect_other_words(p):
    # A pipeline without user_dict must behave exactly as before.
    assert p.convert("銀行") == "ngan4 hong4"
    assert p.convert("香港") == "hoeng1 gong2"


def test_override_scoped_to_its_own_pipeline_instance():
    p1 = Pipeline(user_dict={"正經": "zing1 ging1"})
    p2 = Pipeline()  # no override
    assert p1.convert("正經") == "zing1 ging1"
    assert p2.convert("正經") == "zing3 ging1"


# ── Segmentation interaction ─────────────────────────────────────────────────

def test_override_multi_char_word_not_split_by_segmenter():
    p = Pipeline(user_dict={"老世": "lou5 sai3"})
    detailed = p.convert_detailed("老世要求佢")
    tokens = [tok for tok, _, _, _, _ in detailed]
    assert "老世" in tokens  # not split into "老" + "世"


def test_convert_detailed_reflects_override():
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    detailed = p.convert_detailed("正經嚟講")
    matches = [(tok, jp) for tok, jp, lang, _, _ in detailed if tok == "正經"]
    assert matches == [("正經", "zing1 ging1")]


def test_override_can_be_shadowed_by_a_longer_word_dict_entry():
    # Known limitation of greedy longest-match segmentation: user_dict only
    # competes with word_dict at the SAME starting position. "好正經" is
    # itself a 3-char rime-cantonese entry, so segmenting "佢好正經" matches
    # "好正經" as one token starting at "好" — the "正經" override never gets
    # a chance to compete, because it would have started one character later.
    p = Pipeline(user_dict={"正經": "zing1 ging1"})
    assert p.convert("佢好正經") == "keoi5 hou2 zing3 ging1"  # override NOT applied
    # The same override DOES apply when "正經" is not shadowed this way.
    assert p.convert("正經嚟講") == "zing1 ging1 lai4 gong2"


# ── Empty / absent user_dict is a no-op ─────────────────────────────────────

def test_no_user_dict_behaves_like_before(p):
    assert p.convert("你好嘅，I love Hong Kong") == "nei5 hou2 ge3 ， I love Hong Kong"


def test_empty_user_dict_dict_behaves_like_none():
    p1 = Pipeline(user_dict={})
    p2 = Pipeline()
    assert p1.convert("香港") == p2.convert("香港")


# ── Validation (ValueError at construction time) ────────────────────────────

def test_syllable_count_mismatch_raises():
    with pytest.raises(ValueError, match="syllable"):
        Pipeline(user_dict={"老世": "lou5"})  # 2 chars, 1 syllable


def test_invalid_syllable_raises():
    with pytest.raises(ValueError, match="Jyutping syllable"):
        Pipeline(user_dict={"行": "xyz9"})


def test_empty_key_raises():
    with pytest.raises(ValueError):
        Pipeline(user_dict={"": "zing1"})


def test_valid_multi_syllable_entry_does_not_raise():
    # Should not raise — exercises the happy path through validation.
    Pipeline(user_dict={"老世": "lou5 sai3", "行": "hong4"})
