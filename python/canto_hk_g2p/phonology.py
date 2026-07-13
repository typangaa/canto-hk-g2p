"""LSHK Jyutping phonological inventory and syllable segmentation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# 19 onsets, sorted longest-first so multi-char onsets (ng, gw, kw) match
# before single-character onsets during greedy segmentation.
ONSETS: tuple[str, ...] = tuple(
    sorted(
        ["b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "ng", "h",
         "gw", "kw", "w", "z", "c", "s", "j"],
        key=len,
        reverse=True,
    )
)

RIMES: frozenset[str] = frozenset("""
a aa aai aau aam aan aang aap aat aak
ai au am an ang ap at ak
e ei eu em eng ep et ek
i iu im in ing ip it ik
o oi ou om on ong op ot ok
oe oeng oet oek
eoi eon eot
u ui un ung ut uk
yu yun yut
m ng
""".split())

# Nasals that form a complete syllable on their own (null onset).
SYLLABIC: frozenset[str] = frozenset({"m", "ng"})

TONES: tuple[str, ...] = ("1", "2", "3", "4", "5", "6")

# A valid Jyutping syllable: one or more lowercase letters + a tone digit 1-6.
_SYL_RE = re.compile(r"^[a-z]+[1-6]$")


@dataclass(frozen=True)
class Syllable:
    """A Jyutping syllable decomposed into onset, rime, and tone.

    ``onset`` is ``None`` for null-onset syllables (e.g. ``aa3``, ``o3``)
    and syllabic nasals (e.g. ``m4``, ``ng4``).
    """
    onset: Optional[str]
    rime: str
    tone: str


@dataclass(frozen=True)
class Inventory:
    """The LSHK Jyutping phonological inventory (immutable)."""
    onsets: tuple[str, ...]
    rimes: frozenset[str]
    tones: tuple[str, ...]
    syllabic: frozenset[str]


_INVENTORY = Inventory(
    onsets=ONSETS,
    rimes=RIMES,
    tones=TONES,
    syllabic=SYLLABIC,
)


def inventory() -> Inventory:
    """Return the LSHK Jyutping phonological inventory.

    The returned object is a singleton; callers may cache the reference.

    Example::

        inv = canto_hk_g2p.inventory()
        inv.onsets    # ('ng', 'gw', 'kw', 'b', 'p', ...)  19 onsets, longest-first
        inv.rimes     # frozenset of 61 valid rimes
        inv.tones     # ('1', '2', '3', '4', '5', '6')
        inv.syllabic  # frozenset({'m', 'ng'})
    """
    return _INVENTORY


def segment(syllable: str) -> Optional[Syllable]:
    """Decompose a Jyutping syllable string into ``(onset, rime, tone)``.

    Returns ``None`` if *syllable* is not a valid Jyutping syllable.

    Algorithm:
      1. Validate format: ``^[a-z]+[1-6]$``
      2. Strip the trailing tone digit.
      3. If the body is a syllabic nasal (``m``, ``ng``) → null onset.
      4. Try each onset longest-first; validate the remainder against RIMES.
      5. Try the body as a null-onset rime (e.g. ``aa``, ``o``, ``ai``).
      6. Return ``None`` if nothing matched.

    Example::

        canto_hk_g2p.segment("ngo5")   # Syllable(onset='ng', rime='o', tone='5')
        canto_hk_g2p.segment("aa3")    # Syllable(onset=None, rime='aa', tone='3')
        canto_hk_g2p.segment("m4")     # Syllable(onset=None, rime='m', tone='4')
        canto_hk_g2p.segment("xyz")    # None
    """
    if not _SYL_RE.match(syllable):
        return None
    tone = syllable[-1]
    body = syllable[:-1]

    if body in SYLLABIC:
        return Syllable(onset=None, rime=body, tone=tone)

    for on in ONSETS:
        if body.startswith(on):
            rest = body[len(on):]
            if rest in RIMES:
                return Syllable(onset=on, rime=rest, tone=tone)

    if body in RIMES:
        return Syllable(onset=None, rime=body, tone=tone)

    return None
