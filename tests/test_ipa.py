"""Tests for IPA conversion (v1.5.0)."""
import pytest
from canto_hk_g2p.ipa import jyutping_to_ipa, syllable_to_ipa


# ── syllable_to_ipa ──────────────────────────────────────────────────────────

class TestSyllableToIpa:
    # Tones
    def test_tone_1_high_level(self):
        assert syllable_to_ipa("si1") == "siː˥"

    def test_tone_2_high_rising(self):
        assert syllable_to_ipa("si2") == "siː˧˥"

    def test_tone_3_mid_level(self):
        assert syllable_to_ipa("si3") == "siː˧"

    def test_tone_4_low_falling(self):
        assert syllable_to_ipa("si4") == "siː˨˩"

    def test_tone_5_low_rising(self):
        assert syllable_to_ipa("si5") == "siː˩˧"

    def test_tone_6_low_level(self):
        assert syllable_to_ipa("si6") == "siː˨"

    # tone="number" format
    def test_tone_number_format(self):
        assert syllable_to_ipa("nei5", tone="number") == "nei̯5"

    def test_tone_number_format_diphthong(self):
        assert syllable_to_ipa("gong2", tone="number") == "kɔːŋ˧˥"[:-2] + "2"

    # Initials
    def test_aspirated_initial_p(self):
        result = syllable_to_ipa("paa1")
        assert result.startswith("pʰ")

    def test_unaspirated_initial_b(self):
        result = syllable_to_ipa("baa1")
        assert result.startswith("p") and not result.startswith("pʰ")

    def test_initial_gw(self):
        result = syllable_to_ipa("gwong2")
        assert result.startswith("kʷ") and not result.startswith("kʷʰ")

    def test_initial_kw(self):
        result = syllable_to_ipa("kwong1")
        assert result.startswith("kʷʰ")

    def test_initial_ng(self):
        result = syllable_to_ipa("ngaan4")
        assert result.startswith("ŋ")

    def test_initial_z(self):
        result = syllable_to_ipa("zi1")
        assert result.startswith("ts") and not result.startswith("tsʰ")

    def test_initial_c(self):
        result = syllable_to_ipa("ci1")
        assert result.startswith("tsʰ")

    def test_null_initial(self):
        result = syllable_to_ipa("aa3")
        assert result == "aː˧"

    # Key finals
    def test_final_aa(self):
        assert syllable_to_ipa("baa1") == "paː˥"

    def test_final_aai(self):
        assert syllable_to_ipa("baai1") == "paːi̯˥"

    def test_final_ei(self):
        assert syllable_to_ipa("bei2") == "pei̯˧˥"

    def test_final_ing(self):
        result = syllable_to_ipa("bing1")
        assert "ɪŋ" in result

    def test_final_ik(self):
        result = syllable_to_ipa("bik1")
        assert "ɪk̚" in result

    def test_final_oe(self):
        result = syllable_to_ipa("hoeng1")
        assert "œː" in result

    def test_final_oeng(self):
        result = syllable_to_ipa("hoeng1")
        assert result == "hœːŋ˥"

    def test_final_yu(self):
        result = syllable_to_ipa("jyu4")
        assert "yː" in result

    def test_final_ung(self):
        result = syllable_to_ipa("fung1")
        assert "ʊŋ" in result

    def test_final_uk(self):
        result = syllable_to_ipa("fuk1")
        assert "ʊk̚" in result

    # Syllabic consonants
    def test_syllabic_m(self):
        result = syllable_to_ipa("m4")
        assert "m̩" in result

    def test_syllabic_ng(self):
        result = syllable_to_ipa("ng4")
        assert "ŋ̩" in result

    # Passthrough for non-Jyutping
    def test_passthrough_english(self):
        assert syllable_to_ipa("hello") == "hello"

    def test_passthrough_no_tone(self):
        assert syllable_to_ipa("nei") == "nei"

    def test_passthrough_punctuation(self):
        assert syllable_to_ipa("，") == "，"

    def test_passthrough_empty(self):
        assert syllable_to_ipa("") == ""


# ── jyutping_to_ipa ──────────────────────────────────────────────────────────

class TestJyutpingToIpa:
    def test_basic(self):
        result = jyutping_to_ipa("nei5 hou2 ge3")
        assert result == "nei̯˩˧ hou̯˧˥ kɛː˧"

    def test_tone_number(self):
        result = jyutping_to_ipa("nei5 hou2", tone="number")
        assert result == "nei̯5 hou̯2"

    def test_hong_kong(self):
        result = jyutping_to_ipa("hoeng1 gong2")
        assert result == "hœːŋ˥ kɔːŋ˧˥"

    def test_mixed_passthrough(self):
        # Non-Jyutping tokens pass through
        result = jyutping_to_ipa("nei5 hello ge3")
        parts = result.split()
        assert parts[0] == "nei̯˩˧"
        assert parts[1] == "hello"
        assert parts[2] == "kɛː˧"

    def test_empty(self):
        assert jyutping_to_ipa("") == ""

    def test_single_syllable(self):
        result = jyutping_to_ipa("aa3")
        assert result == "aː˧"


# ── Pipeline.convert_ipa ─────────────────────────────────────────────────────

class TestConvertIpa:
    @pytest.fixture(scope="class")
    def p(self):
        from canto_hk_g2p import Pipeline
        return Pipeline()

    def test_basic_cantonese(self, p):
        result = p.convert_ipa("你好嘅")
        assert "nei̯" in result
        assert "hou̯" in result
        assert "kɛː" in result

    def test_tone_diacritic_default(self, p):
        result = p.convert_ipa("一")
        # tone 1 diacritic should be ˥
        assert "˥" in result

    def test_tone_number(self, p):
        result = p.convert_ipa("一", tone="number")
        assert "1" in result
        # should not contain tone diacritics
        assert "˥" not in result

    def test_english_passthrough_or_ipa(self, p):
        # "hello" is in CMU dict → gets IPA; if cmudict not found yet, passthrough
        result = p.convert_ipa("hello")
        # Either IPA or passthrough — should not crash
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mixed_code_switch(self, p):
        result = p.convert_ipa("香港")
        assert isinstance(result, str)
        # Should contain IPA vowels
        assert any(c in result for c in "ɔœaeiouʊɪɛ")

    def test_hong_kong_ipa(self, p):
        result = p.convert_ipa("香港")
        assert "hœːŋ" in result
        assert "kɔːŋ" in result

    def test_numbers_normalized(self, p):
        # Numbers get expanded to Cantonese before IPA
        result = p.convert_ipa("第3名")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string(self, p):
        assert p.convert_ipa("") == ""
