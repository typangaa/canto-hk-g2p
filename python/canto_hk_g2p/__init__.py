from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional

from ._canto_hk_g2p import PyPipeline as _PyPipeline
from .ipa import jyutping_to_ipa as jyutping_to_ipa  # re-export

__all__ = ["Pipeline", "jyutping_to_ipa"]

try:
    __version__ = version("canto-hk-g2p")
except PackageNotFoundError:
    __version__ = "unknown"

# Bundled data directory (inside the installed package).
# Falls back to None → Rust uses cwd/data/ (local dev workflow).
_PACKAGE_DATA = Path(__file__).parent / "data"
_DATA_DIR: Optional[str] = str(_PACKAGE_DATA) if _PACKAGE_DATA.exists() else None


class Pipeline:
    """Cantonese text-to-Jyutping (G2P) pipeline.

    Loads binary dictionaries from data/ at construction. Zero runtime
    dependencies beyond the compiled Rust extension.

    Args:
        punc_norm: If True (default), run punctuation normalisation before G2P.
            Converts exotic punctuation (「」《》…——) to plain Cantonese equivalents
            that produce clean TTS output. Set to False to disable.

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
    """

    def __init__(self, *, punc_norm: bool = True) -> None:
        self._inner = _PyPipeline(punc_norm=punc_norm, data_dir=_DATA_DIR)

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

    def convert_detailed(self, text: str) -> list[tuple[str, str, str]]:
        """Convert text to a list of (token, jyutping, lang) triples.

        Provides token-level structured output for downstream processing.

        Args:
            text: Input text (Cantonese, English, or mixed).

        Returns:
            List of ``(token, jyutping, lang)`` tuples, one per token.
            ``lang`` is one of:

              - ``"yue"``   — Cantonese CJK token
              - ``"en"``    — Latin/English token (jyutping == token, passthrough)
              - ``"punct"`` — punctuation or other symbol

        Example::

            p.convert_detailed("香港 hello")
            # → [("香港", "hoeng1 gong2", "yue"), ("hello", "hello", "en")]
        """
        return self._inner.convert_detailed(text)

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
        for token, jyutping, lang in self._inner.convert_detailed(text):
            if lang == "yue":
                ipa_syls = [syllable_to_ipa(syl, tone) for syl in jyutping.split()]
                parts.append(" ".join(ipa_syls))
            elif lang == "en":
                parts.append(english_word_to_ipa(token))
            else:
                parts.append(token)
        return " ".join(parts)

