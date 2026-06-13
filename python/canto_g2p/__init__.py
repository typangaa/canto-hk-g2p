from ._canto_g2p import PyPipeline as _PyPipeline

__all__ = ["Pipeline"]
__version__ = "0.1.0"


class Pipeline:
    """Cantonese text-to-Jyutping (G2P) pipeline.

    Loads binary dictionaries from data/ at construction. Zero runtime
    dependencies beyond the compiled Rust extension.

    Example::

        from canto_g2p import Pipeline
        p = Pipeline()
        p.convert("你好嘅，I love Hong Kong")
        # → "nei5 hou2 ge3 , I love hoeng1 gong2"

        p.convert("2026年6月13日")
        # → "ji6 ling4 ji6 luk6 nin4 luk6 jyut6 sap6 saam1 jat6"

        p.convert_batch(["香港", "銀行"])
        # → ["hoeng1 gong2", "ngan4 hong4"]

        p.convert_detailed("香港 hello")
        # → [("香港", "hoeng1 gong2", "yue"), ("hello", "haa1 lou2", "en")]
    """

    def __init__(self) -> None:
        self._inner = _PyPipeline()

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
              - ``"en"``    — Latin/English token
              - ``"punct"`` — punctuation or other symbol

        Example::

            p.convert_detailed("香港 hello")
            # → [("香港", "hoeng1 gong2", "yue"), ("hello", "haa1 lou2", "en")]
        """
        return self._inner.convert_detailed(text)
