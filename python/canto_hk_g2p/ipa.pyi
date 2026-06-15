from typing import Literal

def syllable_to_ipa(
    syllable: str,
    tone: Literal["diacritic", "number"] = "diacritic",
) -> str: ...

def jyutping_to_ipa(
    jyutping: str,
    tone: Literal["diacritic", "number"] = "diacritic",
) -> str: ...
