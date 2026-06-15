from __future__ import annotations

from typing import Literal

_INITIALS: dict[str, str] = {
    "b": "p", "p": "pʰ", "m": "m", "f": "f",
    "d": "t", "t": "tʰ", "n": "n", "l": "l",
    "g": "k", "k": "kʰ", "ng": "ŋ", "h": "h",
    "gw": "kʷ", "kw": "kʷʰ", "w": "w",
    "z": "ts", "c": "tsʰ", "s": "s", "j": "j",
}

_FINALS: dict[str, str] = {
    # aa series
    "aa": "aː", "aai": "aːi̯", "aau": "aːu̯",
    "aam": "aːm", "aan": "aːn", "aang": "aːŋ",
    "aap": "aːp̚", "aat": "aːt̚", "aak": "aːk̚",
    # short a (ɐ)
    "a": "aː",
    "ai": "ɐi̯", "au": "ɐu̯",
    "am": "ɐm", "an": "ɐn", "ang": "ɐŋ",
    "ap": "ɐp̚", "at": "ɐt̚", "ak": "ɐk̚",
    # e series
    "e": "ɛː", "ei": "ei̯", "eu": "ɛːu̯",
    "em": "ɛːm", "eng": "ɛːŋ", "ep": "ɛːp̚", "ek": "ɛːk̚",
    # i series
    "i": "iː", "iu": "iːu̯",
    "im": "iːm", "in": "iːn", "ing": "ɪŋ",
    "ip": "iːp̚", "it": "iːt̚", "ik": "ɪk̚",
    # o series
    "o": "ɔː", "oi": "ɔːi̯", "ou": "ou̯", "on": "ɔːn", "ong": "ɔːŋ",
    "ot": "ɔːt̚", "ok": "ɔːk̚",
    # u series
    "u": "uː", "ui": "uːi̯", "un": "uːn", "ung": "ʊŋ",
    "ut": "uːt̚", "uk": "ʊk̚",
    # oe series (both spellings: eoi/eon/eot per rime-cantonese, oei/oen/oet legacy)
    "oe": "œː", "oei": "œːy̯", "eoi": "œːy̯", "oen": "œːn", "eon": "œːn",
    "oeng": "œːŋ", "oet": "œːt̚", "eot": "œːt̚", "oek": "œːk̚",
    # yu series
    "yu": "yː", "yun": "yːn", "yut": "yːt̚",
}

_SYLLABIC: dict[str, str] = {
    "m": "m̩",
    "ng": "ŋ̩",
}

_TONE_DIACRITIC: dict[str, str] = {
    "1": "˥", "2": "˧˥", "3": "˧",
    "4": "˨˩", "5": "˩˧", "6": "˨",
}

_INITIALS_2 = {"ng", "gw", "kw"}
_INITIALS_1 = set(_INITIALS) - _INITIALS_2


def syllable_to_ipa(syllable: str, tone: Literal["diacritic", "number"] = "diacritic") -> str:
    """Convert a single Jyutping syllable (with tone digit) to IPA.

    Returns the token unchanged if it cannot be parsed as Jyutping.

    Args:
        syllable: A Jyutping syllable with tone number, e.g. "nei5".
        tone: "diacritic" (default) appends IPA suprasegmental marks (˥˧˥…).
              "number" keeps the original tone digit as suffix.

    Returns:
        IPA string, e.g. "nei̯˩˧" or "nei̯5".
    """
    if not syllable or syllable[-1] not in "123456":
        return syllable
    tone_digit = syllable[-1]
    body = syllable[:-1]
    if not body:
        return syllable

    # Syllabic consonants: m4 (唔), ng4, etc.
    if body in _SYLLABIC:
        ipa_body = _SYLLABIC[body]
        if tone == "diacritic":
            return ipa_body + _TONE_DIACRITIC[tone_digit]
        return ipa_body + tone_digit

    # Try 2-char initial first (longest match)
    initial = ""
    final = body
    if len(body) >= 3 and body[:2] in _INITIALS_2:
        initial = body[:2]
        final = body[2:]
    elif body[:1] in _INITIALS_1:
        initial = body[:1]
        final = body[1:]

    if final not in _FINALS:
        return syllable  # unparseable — passthrough

    ipa_body = _INITIALS.get(initial, "") + _FINALS[final]
    if tone == "diacritic":
        return ipa_body + _TONE_DIACRITIC[tone_digit]
    return ipa_body + tone_digit


def jyutping_to_ipa(jyutping: str, tone: Literal["diacritic", "number"] = "diacritic") -> str:
    """Convert space-separated Jyutping to IPA.

    Non-Jyutping tokens (English words, punctuation) pass through unchanged.

    Args:
        jyutping: Space-separated Jyutping string, e.g. "nei5 hou2 ge3".
        tone: "diacritic" uses IPA suprasegmental tone marks (default).
              "number" keeps Jyutping tone digit as suffix.

    Returns:
        Space-separated IPA string, e.g. "nei̯˩˧ hɐu̯˧˥ kɛː˧".

    Example::

        from canto_hk_g2p.ipa import jyutping_to_ipa
        jyutping_to_ipa("nei5 hou2 ge3")
        # → "nei̯˩˧ hɐu̯˧˥ kɛː˧"
        jyutping_to_ipa("nei5 hou2 ge3", tone="number")
        # → "nei̯5 hɐu̯2 kɛː3"
    """
    return " ".join(syllable_to_ipa(tok, tone) for tok in jyutping.split())
