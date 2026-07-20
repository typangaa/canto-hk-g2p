from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

from ._canto_hk_g2p import PyPipeline as _PyPipeline
from .ipa import jyutping_to_ipa as jyutping_to_ipa  # re-export
from .phonology import Inventory as Inventory  # re-export
from .phonology import Syllable as Syllable  # re-export
from .phonology import inventory as inventory  # re-export
from .phonology import segment as segment  # re-export

__all__ = ["Pipeline", "jyutping_to_ipa", "inventory", "segment", "Syllable", "Inventory"]

try:
    __version__ = version("canto-hk-g2p")
except PackageNotFoundError:
    __version__ = "unknown"

# Bundled data directory (inside the installed package).
# Falls back to None → Rust uses cwd/data/ (local dev workflow).
_PACKAGE_DATA = Path(__file__).parent / "data"
_DATA_DIR: Optional[str] = str(_PACKAGE_DATA) if _PACKAGE_DATA.exists() else None


def _validate_user_dict(user_dict: dict[str, str]) -> None:
    """Raise ``ValueError`` on the first malformed ``user_dict`` entry.

    A value is well-formed when it has exactly as many space-separated
    syllables as the key has characters, and every syllable parses via
    :func:`segment`. Validating here (construction time) means a typo
    surfaces immediately instead of silently producing wrong `convert()`
    output later.
    """
    for key, value in user_dict.items():
        if not key:
            raise ValueError("user_dict key must not be empty")
        syllables = value.split()
        if len(syllables) != len(key):
            raise ValueError(
                f"user_dict[{key!r}] = {value!r} has {len(syllables)} syllable(s) "
                f"but {key!r} has {len(key)} character(s) — must match 1:1"
            )
        for syl in syllables:
            if segment(syl) is None:
                raise ValueError(
                    f"user_dict[{key!r}] = {value!r} contains an invalid "
                    f"Jyutping syllable: {syl!r}"
                )


class Pipeline:
    """Cantonese text-to-Jyutping (G2P) pipeline.

    Loads binary dictionaries from data/ at construction. Zero runtime
    dependencies beyond the compiled Rust extension.

    Args:
        punc_norm: If True (default), run punctuation normalisation before G2P.
            Converts exotic punctuation (「」《》…——) to plain Cantonese equivalents
            that produce clean TTS output. Set to False to disable.
        user_dict: Optional runtime override dictionary mapping a word or
            character to a space-separated Jyutping reading, e.g.
            ``{"老世": "lou5 sai3"}``. Takes priority over every bundled
            dictionary (rime-cantonese, ToJyutping, ``oral_hk.tsv``) and also
            participates in segmentation, so a multi-char override is never
            silently split apart before lookup. Each value is validated at
            construction time: the number of space-separated syllables must
            equal the number of characters in the key, and every syllable
            must be a well-formed Jyutping syllable (see :func:`segment`).
            Raises ``ValueError`` immediately on a malformed entry, rather
            than producing wrong output later at ``convert()`` time.

    Example::

        from canto_hk_g2p import Pipeline
        p = Pipeline()
        p.convert("你好嘅，I love Hong Kong")
        # → "nei5 hou2 ge3 ， I love Hong Kong"

        p.convert("《天氣之子》——一個故事")
        # → "tin1 hei3 zi1 zi2 ， jat1 go3 gu3 si6"  (brackets/dash normalised)

        p.convert("2026年6月13日")
        # → "ji6 ling4 ji6 luk6 nin4 luk6 jyut6 sap6 saam1 jat6"

        p.convert_batch(["香港", "銀行"])
        # → ["hoeng1 gong2", "ngan4 hong4"]

        p.convert_detailed("香港 hello")
        # → [("香港", "hoeng1 gong2", "yue"), ("hello", "hello", "en")]

        # Disable punctuation normalisation:
        p2 = Pipeline(punc_norm=False)
        p2.convert("《天氣》")
        # → "《 tin1 hei3 》"

        # Override a reading (e.g. lock a register-specific pronunciation,
        # or teach the pipeline a word missing from the bundled dictionaries):
        p3 = Pipeline(user_dict={"行": "hong4", "老世": "lou5 sai3"})
        p3.convert("行為")     # → "hong4 wai4"   (overridden, not "haang4 wai4")
        p3.convert("老世")     # → "lou5 sai3"    (not in any bundled dict at all)
    """

    def __init__(
        self,
        *,
        punc_norm: bool = True,
        user_dict: Optional[dict[str, str]] = None,
    ) -> None:
        if user_dict:
            _validate_user_dict(user_dict)
        self._inner = _PyPipeline(
            punc_norm=punc_norm, data_dir=_DATA_DIR, user_dict=user_dict
        )

    def convert(self, text: str) -> str:
        """Convert a single string to space-separated Jyutping.

        Numbers, dates and percent signs are expanded to Cantonese spoken form
        before lookup. English/Latin tokens are passed through unchanged.

        Args:
            text: Input text (Cantonese, English, or mixed).

        Returns:
            Space-separated Jyutping string with tone numbers (LSHK standard).
        """
        return self._inner.convert(text)

    def convert_batch(self, texts: list[str]) -> list[str]:
        """Convert a list of strings in parallel using Rayon.

        Args:
            texts: List of input strings.

        Returns:
            List of Jyutping strings, same length and order as input.
        """
        return self._inner.convert_batch(texts)

    def convert_detailed(
        self, text: str
    ) -> list[tuple[str, str, str, str, str]]:
        """Convert text to a list of (token, jyutping, lang, confidence, source) tuples.

        Provides token-level structured output for downstream processing.
        ``jyutping`` is always the rank-0 (most-likely) reading — see
        :meth:`convert_candidates` for the full rank-ordered candidate list.

        Args:
            text: Input text (Cantonese, English, or mixed).

        Returns:
            List of ``(token, jyutping, lang, confidence, source)`` tuples,
            one per token. ``lang`` is one of:

              - ``"yue"``   — Cantonese CJK token
              - ``"en"``    — Latin/English token (jyutping == token, passthrough)
              - ``"punct"`` — punctuation or other symbol

            ``confidence``/``source`` are described on :meth:`convert_candidates`.

        Example::

            p.convert_detailed("香港 hello")
            # → [("香港", "hoeng1 gong2", "yue", "certain", "rime"),
            #     ("hello", "hello", "en", "certain", "passthrough")]
        """
        return self._inner.convert_detailed(text)

    def convert_detailed_batch(
        self, texts: list[str]
    ) -> list[list[tuple[str, str, str, str, str]]]:
        """Convert a list of strings in parallel using Rayon.

        Batch sibling of :meth:`convert_detailed` — same per-text output
        shape, one list of ``(token, jyutping, lang, confidence, source)``
        tuples per input text.

        Args:
            texts: List of input strings.

        Returns:
            List of per-text ``convert_detailed()`` results, same length
            and order as ``texts``.
        """
        return self._inner.convert_detailed_batch(texts)

    def convert_candidates(
        self, text: str
    ) -> list[tuple[str, list[str], str, str, str]]:
        """Convert text to a list of (token, candidate_readings, lang, confidence, source) tuples.

        Surfaces every known alternate reading for a polyphone (多音字) instead
        of committing to a single one — for downstream uses like letting a
        human or a downstream model pick, or auditing where the bundled
        dictionaries had to make a judgment call.

        ``candidate_readings`` is rank-ordered (most-likely first). It has more
        than one entry only where the bundled data has 2+ known readings for
        that exact token (or, for an out-of-vocabulary single character, that
        character). Unambiguous words, English tokens, punctuation, and
        out-of-vocabulary multi-char tokens (resolved per-character — see
        CHANGELOG) all report a single-item list, identical to what
        :meth:`convert_detailed` would produce for that token.

        A ``user_dict`` override always collapses to a single candidate: an
        override is a final decision, not ambiguity to report.

        ``confidence`` is one of:

        - ``"certain"``: a single known reading; no ambiguity to report.
        - ``"ranked"``: 2+ candidates, ordered by ToJyutping's own
          context-aware ranking — a real preference signal.
        - ``"tied"``: 2+ candidates, but the order is rime-cantonese's raw
          arbitrary tie-break — no real preference signal. Also the default
          for an ambiguous token when the bundled confidence data has no
          entry for it.

        No numeric probability is exposed by design: neither ToJyutping's
        trie nor rime-cantonese's tied readings carry real frequency data,
        so a float score would be fabricated rather than measured. See
        CHANGELOG for the research behind this categorical-only design
        (`#12 <https://github.com/typangaa/canto-hk-g2p/issues/12>`_).

        ``source`` names the data layer that produced ``candidate_readings[0]``
        (`#13 <https://github.com/typangaa/canto-hk-g2p/issues/13>`_):

        - ``"rime"``: rime-cantonese dictionary entry.
        - ``"tojyutping"``: exact ToJyutping trie rank-0 hit.
        - ``"tojyutping_tiebreak"``: a rime-cantonese arbitrary tie resolved
          via ToJyutping's context-aware segmentation (v1.7.1).
        - ``"oral_hk"``: hand-curated HK colloquial override.
        - ``"variant_alias"``: a 借音字 (phonetic-loan miswriting, e.g. 訓覺
          for 瞓覺) resolved by copying the correctly-spelled canonical
          word's reading (`data/variant_words.tsv`, v2.1.0).
        - ``"hkcancor_verified"``: a 變調 (changed-tone) word-level override
          whose spoken tone was found to differ from the citation tone via
          diffing HKCanCor's transcribed corpus against the citation
          reading, then confirmed by a native speaker (`data/tone_sandhi_words.tsv`,
          v2.2.0). Word-level only — the underlying characters keep their
          citation reading in other, unrelated compounds.
        - ``"unihan"``: Unihan ``kCantonese`` char-only fallback.
        - ``"user_dict"``: caller-supplied runtime override.
        - ``"passthrough"``: non-CJK token (English, punctuation, digits).
        - ``"char_fallback"``: an out-of-vocabulary multi-char token resolved
          via the per-character fallback loop — architecturally unreachable
          through real segmenter output (see CHANGELOG known limitation).
        - ``"unresolved"``: a truly unknown character, kept as-is.
        - ``"unknown"``: the source sidecar has no entry (or is missing) for
          an otherwise-resolved dict hit — older/custom data directories.

        Args:
            text: Input text (Cantonese, English, or mixed).

        Returns:
            List of ``(token, candidate_readings, lang, confidence, source)``
            tuples, one per token.

        Example::

            p.convert_candidates("正經")
            # → [("正經", ["zing3 ging1", "zing1 ging1"], "yue", "tied", "tojyutping_tiebreak")]

            p.convert_candidates("香港")
            # → [("香港", ["hoeng1 gong2"], "yue", "certain", "rime")]   (no known ambiguity)
        """
        return self._inner.convert_candidates(text)

    def convert_candidates_batch(
        self, texts: list[str]
    ) -> list[list[tuple[str, list[str], str, str, str]]]:
        """Convert a list of strings in parallel using Rayon.

        Batch sibling of :meth:`convert_candidates` — same per-text output
        shape, one list of ``(token, candidate_readings, lang, confidence,
        source)`` tuples per input text.

        Args:
            texts: List of input strings.

        Returns:
            List of per-text ``convert_candidates()`` results, same length
            and order as ``texts``.

        Example::

            p.convert_candidates_batch(["正經", "香港"])
            # → [
            #      [("正經", ["zing3 ging1", "zing1 ging1"], "yue", "tied", "tojyutping_tiebreak")],
            #      [("香港", ["hoeng1 gong2"], "yue", "certain", "rime")],
            #    ]
        """
        return self._inner.convert_candidates_batch(texts)

    def convert_ipa(
        self,
        text: str,
        tone: str = "diacritic",
    ) -> str:
        """Convert text to IPA (International Phonetic Alphabet).

        Uses Jyutping→IPA mapping for Cantonese tokens and the CMU Pronouncing
        Dictionary for English tokens. Non-dictionary English words pass through
        unchanged.

        Args:
            text: Input text (Cantonese, English, or mixed).
            tone: "diacritic" (default) — IPA suprasegmental tone marks (˥˧˥˧˨˩˩˧˨).
                  "number" — IPA phonemes with Jyutping tone digit suffix.

        Returns:
            Space-separated IPA string.

        Example::

            p = Pipeline()
            p.convert_ipa("你好嘅")
            # → "nei̯˩˧ hɐu̯˧˥ kɛː˧"

            p.convert_ipa("你好嘅", tone="number")
            # → "nei̯5 hɐu̯2 kɛː3"

            p.convert_ipa("佢 send 咗 email 俾我")
            # → "kʰɵy̯˨ sɛnd tsɔː˧ iːmeɪl pei̯˧˥ ŋɔː˩˧"
        """
        from .ipa import syllable_to_ipa
        from ._cmu import english_word_to_ipa

        parts: list[str] = []
        for token, jyutping, lang, _, _ in self._inner.convert_detailed(text):
            if lang == "yue":
                ipa_syls = [syllable_to_ipa(syl, tone) for syl in jyutping.split()]
                parts.append(" ".join(ipa_syls))
            elif lang == "en":
                parts.append(english_word_to_ipa(token))
            else:
                parts.append(token)
        return " ".join(parts)

