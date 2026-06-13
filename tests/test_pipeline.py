"""
Phase 1 G2P tests — real dictionary loaded from data/word.bin + data/char.bin.

Run from repo root:  pytest tests/ -v
The data/ dir must exist (run python3 scripts/build_dict.py first).
"""
import pytest
from canto_hk_g2p import Pipeline


@pytest.fixture(scope="module")
def p():
    return Pipeline()


# ── Basic correctness ────────────────────────────────────────────────────────

def test_empty_string(p):
    assert p.convert("") == ""


def test_cantonese_particle_ge3(p):
    # 嘅 = oral_hk override → ge3
    assert p.convert("嘅") == "ge3"


def test_cantonese_particle_hai2(p):
    assert p.convert("喺") == "hai2"


def test_cantonese_negation_m4(p):
    assert p.convert("唔") == "m4"


def test_hongkong(p):
    assert p.convert("香港") == "hoeng1 gong2"


def test_polyphone_ngaan_hong4(p):
    # 銀行 → ngan4 hong4 (not ngan4 haang4) — word-level dict resolves polyphone
    assert p.convert("銀行") == "ngan4 hong4"


# ── English passthrough (v1: Latin tokens unchanged) ────────────────────────

def test_english_passthrough_single(p):
    assert p.convert("hello") == "hello"  # Latin tokens pass through, never touch dict


def test_english_pure_ascii_phrase(p):
    # Pure English words with no Cantonese chars → pass through as-is
    result = p.convert("I love Hong Kong")
    assert result == "I love Hong Kong"


def test_mixed_code_switch(p):
    # 佢send咗email俾我 — English loanwords have Cantonese readings in rime-cantonese
    result = p.convert("佢send咗email俾我")
    assert isinstance(result, str)
    assert "keoi5" in result   # 佢
    assert "zo2" in result     # 咗
    assert "bei2" in result    # 俾
    assert "ngo5" in result    # 我


# ── Batch processing ─────────────────────────────────────────────────────────

def test_batch_matches_single(p):
    inputs = ["香港", "嘅", "唔", "銀行"]
    assert p.convert_batch(inputs) == [p.convert(t) for t in inputs]


def test_batch_empty_list(p):
    assert p.convert_batch([]) == []


def test_batch_with_empty_string(p):
    result = p.convert_batch(["香港", "", "唔"])
    assert result[0] == "hoeng1 gong2"
    assert result[1] == ""
    assert result[2] == "m4"


# ── Output type guarantees ───────────────────────────────────────────────────

def test_output_is_always_str(p):
    for text in ["你好", "hello", "123", "，", ""]:
        assert isinstance(p.convert(text), str)


def test_pipeline_is_reusable(p):
    # Same pipeline instance gives same results across calls
    assert p.convert("香港") == p.convert("香港")
