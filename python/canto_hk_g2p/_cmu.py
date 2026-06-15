from __future__ import annotations

from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent / "data"
_CMUDICT_PATH = _DATA_DIR / "cmudict.dict"

# ARPAbet phoneme (stress stripped) → IPA
_ARPABET: dict[str, str] = {
    "AA": "ɑː", "AE": "æ",  "AH": "ʌ",  "AO": "ɔː",
    "AW": "aʊ", "AY": "aɪ", "B":  "b",   "CH": "tʃ",
    "D":  "d",  "DH": "ð",  "EH": "ɛ",  "ER": "ɜː",
    "EY": "eɪ", "F":  "f",  "G":  "ɡ",   "HH": "h",
    "IH": "ɪ",  "IY": "iː", "JH": "dʒ", "K":  "k",
    "L":  "l",  "M":  "m",  "N":  "n",   "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P":  "p",   "R":  "ɹ",
    "S":  "s",  "SH": "ʃ",  "T":  "t",   "TH": "θ",
    "UH": "ʊ",  "UW": "uː", "V":  "v",   "W":  "w",
    "Y":  "j",  "Z":  "z",  "ZH": "ʒ",
}

# Unstressed vowel overrides (stress digit 0)
_ARPABET_UNSTRESSED: dict[str, str] = {
    "AH": "ə",
    "ER": "ɚ",
}

_dict_cache: Optional[dict[str, list[str]]] = None


def _load() -> dict[str, list[str]]:
    global _dict_cache
    if _dict_cache is not None:
        return _dict_cache
    d: dict[str, list[str]] = {}
    with open(_CMUDICT_PATH, encoding="latin-1") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith(";;;"):
                continue
            parts = line.split()
            if not parts:
                continue
            word = parts[0]
            if "(" in word:
                continue  # skip alternates, keep primary pronunciation
            d[word.lower()] = parts[1:]
    _dict_cache = d
    return d


def _phoneme_to_ipa(phoneme: str) -> str:
    """Convert a single ARPAbet phoneme (with stress digit) to IPA."""
    if phoneme[-1].isdigit():
        stress = phoneme[-1]
        base = phoneme[:-1]
        if stress == "0" and base in _ARPABET_UNSTRESSED:
            return _ARPABET_UNSTRESSED[base]
        return _ARPABET.get(base, phoneme)
    return _ARPABET.get(phoneme, phoneme)


def english_word_to_ipa(word: str) -> str:
    """Convert an English word to IPA using the CMU Pronouncing Dictionary.

    Returns the word unchanged if it is not found in the dictionary (OOV passthrough).

    Args:
        word: An English word (case-insensitive).

    Returns:
        Concatenated IPA string, e.g. "hɛloʊ", or the original word if OOV.
    """
    d = _load()
    phonemes = d.get(word.lower())
    if phonemes is None:
        return word
    return "".join(_phoneme_to_ipa(p) for p in phonemes)
