from typing import Optional

ONSETS: tuple[str, ...]
RIMES: frozenset[str]
SYLLABIC: frozenset[str]
TONES: tuple[str, ...]

class Syllable:
    onset: Optional[str]
    rime: str
    tone: str
    def __init__(self, onset: Optional[str], rime: str, tone: str) -> None: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...

class Inventory:
    onsets: tuple[str, ...]
    rimes: frozenset[str]
    tones: tuple[str, ...]
    syllabic: frozenset[str]
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...

def inventory() -> Inventory: ...
def segment(syllable: str) -> Optional[Syllable]: ...
