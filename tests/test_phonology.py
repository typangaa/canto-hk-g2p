"""Tests for canto_hk_g2p.phonology — inventory() + segment() API."""
import re

import pytest

import canto_hk_g2p as g
from canto_hk_g2p.phonology import Inventory, Syllable, inventory, segment


# ── inventory() ──────────────────────────────────────────────────────────────

class TestInventory:
    def test_singleton(self):
        assert g.inventory() is g.inventory()

    def test_returns_inventory_type(self):
        assert isinstance(g.inventory(), Inventory)

    def test_onset_count(self):
        assert len(g.inventory().onsets) == 19

    def test_rime_count(self):
        assert len(g.inventory().rimes) == 61

    def test_tone_count(self):
        assert len(g.inventory().tones) == 6

    def test_tones_values(self):
        assert set(g.inventory().tones) == {"1", "2", "3", "4", "5", "6"}

    def test_syllabic(self):
        assert g.inventory().syllabic == {"m", "ng"}

    def test_onsets_longest_first(self):
        onsets = g.inventory().onsets
        for i in range(len(onsets) - 1):
            assert len(onsets[i]) >= len(onsets[i + 1]), (
                f"Onset order broken: {onsets[i]!r} before {onsets[i+1]!r}"
            )

    def test_multi_char_onsets_present(self):
        onsets = set(g.inventory().onsets)
        assert "ng" in onsets
        assert "gw" in onsets
        assert "kw" in onsets

    def test_all_known_onsets(self):
        expected = {"b", "p", "m", "f", "d", "t", "n", "l", "g", "k",
                    "ng", "h", "gw", "kw", "w", "z", "c", "s", "j"}
        assert set(g.inventory().onsets) == expected

    def test_known_rimes_present(self):
        rimes = g.inventory().rimes
        for r in ["a", "aa", "aai", "aau", "ai", "au", "ei", "ou",
                  "oi", "oeng", "eoi", "eon", "yu", "yun", "yut",
                  "m", "ng", "ung", "ing"]:
            assert r in rimes, f"Expected rime {r!r} missing from inventory"

    def test_syllabic_subset_of_rimes(self):
        inv = g.inventory()
        assert inv.syllabic <= inv.rimes

    def test_inventory_immutable(self):
        with pytest.raises((AttributeError, TypeError)):
            g.inventory().onsets = ()  # type: ignore[misc]


# ── segment() ────────────────────────────────────────────────────────────────

class TestSegment:
    # ── valid syllables ──

    def test_ng_onset(self):
        assert g.segment("ngo5") == Syllable(onset="ng", rime="o", tone="5")

    def test_null_onset_aa(self):
        assert g.segment("aa3") == Syllable(onset=None, rime="aa", tone="3")

    def test_null_onset_o(self):
        assert g.segment("o3") == Syllable(onset=None, rime="o", tone="3")

    def test_null_onset_ai(self):
        assert g.segment("ai1") == Syllable(onset=None, rime="ai", tone="1")

    def test_syllabic_m(self):
        assert g.segment("m4") == Syllable(onset=None, rime="m", tone="4")

    def test_syllabic_ng(self):
        assert g.segment("ng4") == Syllable(onset=None, rime="ng", tone="4")

    def test_gw_onset(self):
        assert g.segment("gwong2") == Syllable(onset="gw", rime="ong", tone="2")

    def test_kw_onset(self):
        assert g.segment("kwai1") == Syllable(onset="kw", rime="ai", tone="1")

    def test_j_onset(self):
        assert g.segment("jat1") == Syllable(onset="j", rime="at", tone="1")

    def test_h_oeng(self):
        assert g.segment("hoeng1") == Syllable(onset="h", rime="oeng", tone="1")

    def test_eoi_rime(self):
        assert g.segment("zeoi3") == Syllable(onset="z", rime="eoi", tone="3")

    def test_eon_rime(self):
        assert g.segment("seon1") == Syllable(onset="s", rime="eon", tone="1")

    def test_yu_rime(self):
        assert g.segment("jyu1") == Syllable(onset="j", rime="yu", tone="1")

    def test_yun_rime(self):
        assert g.segment("gyun2") == Syllable(onset="g", rime="yun", tone="2")

    def test_lei(self):
        assert g.segment("lei5") == Syllable(onset="l", rime="ei", tone="5")

    def test_nei(self):
        assert g.segment("nei5") == Syllable(onset="n", rime="ei", tone="5")

    def test_all_tones(self):
        for tone in "123456":
            result = g.segment(f"lei{tone}")
            assert result is not None and result.tone == tone

    def test_tone_1(self):
        assert g.segment("san1") == Syllable(onset="s", rime="an", tone="1")

    def test_tone_6(self):
        assert g.segment("gong6") == Syllable(onset="g", rime="ong", tone="6")

    # ── invalid inputs ──

    def test_invalid_xyz(self):
        assert g.segment("xyz") is None

    def test_invalid_empty(self):
        assert g.segment("") is None

    def test_invalid_no_tone(self):
        assert g.segment("nei") is None

    def test_invalid_tone_digit_7(self):
        assert g.segment("nei7") is None

    def test_invalid_tone_digit_0(self):
        assert g.segment("nei0") is None

    def test_invalid_uppercase(self):
        assert g.segment("Nei5") is None

    def test_invalid_space(self):
        assert g.segment("nei5 hou2") is None

    def test_invalid_bad_rime(self):
        assert g.segment("bxyz1") is None

    # ── Syllable properties ──

    def test_syllable_hashable(self):
        s = g.segment("ngo5")
        assert s is not None
        assert {s: True}[s] is True

    def test_syllable_equality(self):
        assert g.segment("ngo5") == g.segment("ngo5")
        assert g.segment("ngo5") != g.segment("lei5")

    def test_syllable_type(self):
        assert isinstance(g.segment("ngo5"), Syllable)

    # ── top-level re-export ──

    def test_top_level_import(self):
        assert g.segment is segment
        assert g.inventory is inventory

    # ── roundtrip: pipeline output must all be segmentable ──

    def test_roundtrip_pipeline_output(self):
        """Every Jyutping syllable emitted by Pipeline must be segmentable."""
        p = g.Pipeline()
        text = "你好嘅，我係香港人，佢哋去邊度？唔該晒！"
        jyutping = p.convert(text)
        syl_re = re.compile(r"^[a-z]+[1-6]$")
        oov = [tok for tok in jyutping.split()
               if syl_re.match(tok) and g.segment(tok) is None]
        assert oov == [], f"Un-segmentable syllables: {oov}"
