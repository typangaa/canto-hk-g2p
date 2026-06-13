from ._canto_g2p import PyPipeline as _PyPipeline

__all__ = ["Pipeline"]
__version__ = "0.1.0"


class Pipeline:
    """Cantonese G2P pipeline.

    Usage::

        from canto_g2p import Pipeline
        p = Pipeline()
        p.convert("你好嘅")          # → "你 好 嘅"  (Phase 0 stub)
        p.convert_batch(["你好", "香港"])
    """

    def __init__(self) -> None:
        self._inner = _PyPipeline()

    def convert(self, text: str) -> str:
        """Convert a single string to Jyutping-annotated output."""
        return self._inner.convert(text)

    def convert_batch(self, texts: list[str]) -> list[str]:
        """Convert a list of strings in parallel (Rayon)."""
        return self._inner.convert_batch(texts)
