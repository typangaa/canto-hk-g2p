#!/usr/bin/env python3
"""
build_dict.py — Build binary dictionary files for canto-g2p.

Reads raw source data and produces two binary .bin files:
  data/word.bin  — all entries (single- and multi-character words)
  data/char.bin  — single-character entries only

Binary format (CJYP v1):
  HEADER  16 bytes : magic(4) version(u32LE) entry_count(u32LE) pool_size(u32LE)
  ENTRIES entry_count × 12 bytes (sorted lexicographically by UTF-8 key):
           key_start(u32LE) key_len(u16LE) val_start(u32LE) val_len(u16LE)
  POOL    UTF-8 strings packed end-to-end, no null terminators.

Run from repo root:
  python3 scripts/build_dict.py
"""

import struct
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

ORAL_HK_TSV = DATA_DIR / "oral_hk.tsv"
VARIANT_WORDS_TSV = DATA_DIR / "variant_words.tsv"
TONE_SANDHI_WORDS_TSV = DATA_DIR / "tone_sandhi_words.tsv"

RIME_FILES: List[Path] = [
    RAW_DIR / "rime-cantonese" / "jyut6ping3.chars.dict.yaml",
    RAW_DIR / "rime-cantonese" / "jyut6ping3.words.dict.yaml",
    RAW_DIR / "rime-cantonese" / "jyut6ping3.lettered.dict.yaml",
    # NOTE: jyut6ping3.phrase.dict.yaml intentionally excluded — it has no
    # `...` YAML separator, so the parser below silently reads 0 entries
    # from it (see scripts/fetch_data.py, which no longer downloads it).
]

UNIHAN_READINGS = RAW_DIR / "unihan" / "Unihan_Readings.txt"

# Output goes into the Python package so maturin bundles them in the wheel.
# data/ at the repo root is kept as a dev fallback (not tracked in git).
PKG_DATA_DIR = REPO_ROOT / "python" / "canto_hk_g2p" / "data"
OUT_WORD_BIN = PKG_DATA_DIR / "word.bin"
OUT_CHAR_BIN = PKG_DATA_DIR / "char.bin"
OUT_WORD_CANDIDATES_BIN = PKG_DATA_DIR / "word_candidates.bin"
OUT_CHAR_CANDIDATES_BIN = PKG_DATA_DIR / "char_candidates.bin"
OUT_WORD_CANDIDATES_CONFIDENCE_BIN = PKG_DATA_DIR / "word_candidates_confidence.bin"
OUT_CHAR_CANDIDATES_CONFIDENCE_BIN = PKG_DATA_DIR / "char_candidates_confidence.bin"
OUT_WORD_SOURCE_BIN = PKG_DATA_DIR / "word_source.bin"
OUT_CHAR_SOURCE_BIN = PKG_DATA_DIR / "char_source.bin"
CMUDICT_SRC = RAW_DIR / "cmudict" / "cmudict.dict"
CMUDICT_DST = PKG_DATA_DIR / "cmudict.dict"

# ---------------------------------------------------------------------------
# Binary format constants
# ---------------------------------------------------------------------------

MAGIC = b"CJYP"
VERSION = 1
HEADER_FMT = "<4sIII"   # magic, version, entry_count, pool_size  -> 16 bytes
ENTRY_FMT = "<IHIH"     # key_start(u32), key_len(u16), val_start(u32), val_len(u16) -> 12 bytes

assert struct.calcsize(HEADER_FMT) == 16, "Header struct size mismatch"
assert struct.calcsize(ENTRY_FMT) == 12, "Entry struct size mismatch"


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def load_oral_hk(path: Path, tag: str = "oral_hk") -> Dict[str, str]:
    """
    Load a TSV of highest-priority overrides (e.g. oral_hk.tsv,
    tone_sandhi_words.tsv). Format:  word<TAB>jyutping
    Skips lines starting with '#' or blank lines.
    If a key appears multiple times, LAST entry wins (so later curations
    override earlier ones within the file — e.g. the two entries for 囉/㗎).
    """
    result: Dict[str, str] = {}
    if not path.exists():
        print(f"[WARN] {path.name} not found: {path}", file=sys.stderr)
        return result

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"[WARN] {path.name}:{lineno}: bad line: {line!r}", file=sys.stderr)
                continue
            word, jyutping = parts[0].strip(), parts[1].strip()
            if word and jyutping:
                result[word] = jyutping  # last occurrence wins

    print(f"[{tag}]   loaded {len(result):,} entries from {path.name}")
    return result


def load_variant_words(path: Path) -> Dict[str, str]:
    """
    Load variant_words.tsv — 借音字 (phonetic-loan) alias overrides.
    Format:  variant_spelling<TAB>canonical_spelling
    Skips lines starting with '#' or blank lines.
    Resolution (copying the canonical spelling's jyutping) happens in main(),
    after word_entries is fully built, since the canonical spelling must
    already be resolved.
    """
    result: Dict[str, str] = {}
    if not path.exists():
        print(f"[WARN] variant_words.tsv not found: {path}", file=sys.stderr)
        return result

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"[WARN] variant_words.tsv:{lineno}: bad line: {line!r}", file=sys.stderr)
                continue
            variant, canonical = parts[0].strip(), parts[1].strip()
            if variant and canonical:
                result[variant] = canonical

    print(f"[variant]   loaded {len(result):,} entries from {path.name}")
    return result


def _parse_weight(weight_str: str) -> int:
    """Parse '5%' -> 5; returns -1 if not a valid weight token."""
    s = weight_str.strip()
    if s.endswith("%"):
        try:
            return int(s[:-1])
        except ValueError:
            pass
    return -1


def load_rime_cantonese(
    paths: List[Path],
) -> Tuple[Dict[str, str], Dict[str, str], Set[str], Dict[str, List[str]]]:
    """
    Load rime-cantonese dict YAML files.

    Returns:
        rime_all     : dict[word -> jyutping]  (all words, single- and multi-char)
        rime_chars    : dict[char -> jyutping]  (single-char entries only)
        rime_tied     : set of words whose picked reading was an ARBITRARY tie-break
                        — i.e. the source YAML had >=2 distinct readings at the same
                        max weight (most commonly: neither has an explicit weight at
                        all, e.g. 正經 appears as both "zing1 ging1" and "zing3 ging1"
                        with no weight column). "First occurrence wins" in that case
                        is not a real disambiguation signal — see resolve_tied_readings().
        rime_readings : dict[word -> list of distinct readings], populated ONLY for
                        words in rime_tied, in first-seen order — the raw candidate
                        material for build_candidates() before ToJyutping/tie-break
                        resolution picks a winner.

    Deduplication rules:
    - Same key in an EARLIER file wins over a LATER file.
    - Within a file, keep the entry with the HIGHEST weight percentage.
      If no weights are given, keep the FIRST occurrence (weight stays -1).
    - We overwrite only when the new candidate weight is strictly greater.
    """
    # Tracks the current best (jyutping, weight) for each key across all files.
    best_all: Dict[str, Tuple[str, int]] = {}
    best_chars: Dict[str, Tuple[str, int]] = {}
    tied_words: Set[str] = set()
    readings_all: Dict[str, List[str]] = {}

    for path in paths:
        if not path.exists():
            print(f"[WARN] rime file not found: {path}", file=sys.stderr)
            continue

        in_data = False  # True after we see the `...` separator
        file_entries = 0

        # Collect per-file best entries before merging (so earlier files lock keys)
        file_best: Dict[str, Tuple[str, int]] = {}
        file_tied: Set[str] = set()
        file_readings: Dict[str, List[str]] = {}

        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n\r")

                if not in_data:
                    if line.strip() == "...":
                        in_data = True
                    continue

                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                word = parts[0].strip()
                jyutping = parts[1].strip()
                if not word or not jyutping:
                    continue

                # No explicit weight → primary reading; must beat any N% entry.
                _NO_WEIGHT = 10000
                weight = _parse_weight(parts[2]) if len(parts) >= 3 else _NO_WEIGHT

                # Within-file: keep highest weight (first occurrence wins on tie)
                if word not in file_best:
                    file_best[word] = (jyutping, weight)
                    file_readings[word] = [jyutping]
                    file_entries += 1
                else:
                    existing_jyut, existing_weight = file_best[word]
                    if weight > existing_weight:
                        file_best[word] = (jyutping, weight)
                        file_tied.discard(word)  # strict new winner — no longer a tie
                        if jyutping not in file_readings[word]:
                            file_readings[word].insert(0, jyutping)
                    elif weight == existing_weight and jyutping != existing_jyut:
                        file_tied.add(word)
                        if jyutping not in file_readings[word]:
                            file_readings[word].append(jyutping)

        # Merge file_best into global dicts — earlier files already won
        new_from_file = 0
        for word, (jyut, w) in file_best.items():
            is_single = len(word) == 1

            if word not in best_all:
                best_all[word] = (jyut, w)
                new_from_file += 1
                if word in file_tied:
                    tied_words.add(word)
                    readings_all[word] = file_readings[word]
            # Keys already in best_all come from an earlier file — do not overwrite

            if is_single and word not in best_chars:
                best_chars[word] = (jyut, w)

        print(
            f"[rime]      {path.name}: {file_entries:,} unique entries in file, "
            f"{new_from_file:,} new added to global dict"
        )

    rime_all = {k: v[0] for k, v in best_all.items()}
    rime_chars = {k: v[0] for k, v in best_chars.items()}
    print(f"[rime]      {len(tied_words):,} words had an arbitrary tie-break (see rime_tied)")
    return rime_all, rime_chars, tied_words, readings_all


def load_unihan(path: Path) -> Dict[str, str]:
    """
    Load Unihan_Readings.txt — fallback for single chars only.
    Only lines where field[1] == 'kCantonese' are used.
    If multiple readings are space-separated, use the FIRST one.
    Converts U+XXXX hex to the actual Unicode character.
    First occurrence per codepoint wins.
    """
    result: Dict[str, str] = {}
    if not path.exists():
        print(f"[WARN] Unihan not found: {path}", file=sys.stderr)
        return result

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            codepoint_str, field_name, field_value = parts[0], parts[1], parts[2]
            if field_name != "kCantonese":
                continue

            if not codepoint_str.startswith("U+"):
                continue
            try:
                cp = int(codepoint_str[2:], 16)
                char = chr(cp)
            except (ValueError, OverflowError):
                continue

            # First reading only
            readings = field_value.strip().split()
            if not readings:
                continue
            jyutping = readings[0]

            # First occurrence wins
            if char not in result:
                result[char] = jyutping

    print(f"[unihan]    loaded {len(result):,} kCantonese entries from {path.name}")
    return result


def load_tojyutping() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Load ToJyutping's trie data (build-time-only dependency, BSD-2-Clause).

    Imports ToJyutping.Trie directly (no raw file fetch needed — the package
    bundles and decodes its own trie.txt at import time). Walks the trie and
    takes the rank-0 (most-likely) candidate reading for every entry, while
    also keeping the full rank-ordered candidate list for entries that have
    more than one — this is the primary source for the Candidates API
    (Phase 7b-2): ToJyutping's own ranking is more trustworthy than our own
    tie-break heuristics because it reflects that package's context modelling.

    Returns:
        tojyutping_all        : dict[word -> jyutping]  (rank-0 reading; all entries)
        tojyutping_chars      : dict[char -> jyutping]  (rank-0 reading; single-char only)
        tojyutping_candidates : dict[word -> [readings]] rank-ordered, only for
                                 entries with 2+ distinct candidate readings
                                 (single- and multi-char)
        tojyutping_char_candidates : same, restricted to single-char keys

    Raises ImportError with a clear message if the `ToJyutping` package is not
    installed (it's a build-time-only dependency, not listed in the wheel's
    runtime requirements — see scripts/fetch_data.py for the pinned version).

    Excludes multi-char words made entirely of bare Chinese digit characters
    (e.g. `二六`, `四六`) — a handful of these carry tone-sandhi'd colloquial
    readings (`ji6 luk1` instead of citation `ji6 luk6`) that collide with our
    own normalizer's digit-by-digit year/number expansion (`digits_to_chars()`
    in src/normalizer.rs emits exactly these character sequences and expects
    citation tones — see CLAUDE.md's locked "v1 skips tone sandhi" decision).
    """
    try:
        import ToJyutping.Trie as T
    except ImportError as exc:
        raise ImportError(
            "ToJyutping is required to build the dictionary but is not installed. "
            "Install it with:  pip install ToJyutping==3.2.0\n"
            "(It is a build-time-only dependency; it is NOT bundled in the wheel.)"
        ) from exc

    BARE_DIGITS = set("零一二三四五六七八九")

    tojyutping_all: Dict[str, str] = {}
    tojyutping_chars: Dict[str, str] = {}
    tojyutping_candidates: Dict[str, List[str]] = {}
    tojyutping_char_candidates: Dict[str, List[str]] = {}

    # Iterative trie walk using an explicit stack to avoid recursion limits.
    stack: List[Tuple[object, str]] = [(T.root, "")]
    while stack:
        node, prefix = stack.pop()
        if node.v:
            if len(prefix) > 1 and all(c in BARE_DIGITS for c in prefix):
                pass  # skip — reserved for our own digit-by-digit normalizer output
            else:
                reading = str(node.v[0])  # rank-0 = most-likely reading
                tojyutping_all[prefix] = reading
                if len(prefix) == 1:
                    tojyutping_chars[prefix] = reading

                # Dedupe consecutive-equal ranks while preserving rank order.
                distinct: List[str] = []
                seen: Set[str] = set()
                for candidate in node.v:
                    s = str(candidate)
                    if s not in seen:
                        seen.add(s)
                        distinct.append(s)
                if len(distinct) > 1:
                    tojyutping_candidates[prefix] = distinct
                    if len(prefix) == 1:
                        tojyutping_char_candidates[prefix] = distinct
        for char, child in node.items():
            stack.append((child, prefix + char))

    print(
        f"[tojyutping] loaded {len(tojyutping_all):,} entries "
        f"({len(tojyutping_chars):,} single-char); "
        f"{len(tojyutping_candidates):,} with 2+ ranked candidates "
        f"({len(tojyutping_char_candidates):,} single-char)"
    )
    return tojyutping_all, tojyutping_chars, tojyutping_candidates, tojyutping_char_candidates


def resolve_tied_readings(tied_words: Set[str]) -> Dict[str, str]:
    """
    Re-disambiguate rime-cantonese words whose reading was an arbitrary
    tie-break (see load_rime_cantonese()'s rime_tied return value).

    load_tojyutping() above only overrides a tied word when it exists as an
    exact node in ToJyutping's trie — about 56% of tied rime words don't
    (e.g. 正經 has no multi-char trie entry, only its individual chars 正/經
    do). This function instead calls ToJyutping.get_jyutping_text(), which
    applies ToJyutping's own context-aware segmentation across the whole
    word rather than a single exact-match lookup, and resolves most of the
    remainder correctly (verified: 345/537 valid-format cases changed the
    pick, cross-checked against the tied candidates during Phase 7a.1 dev).

    Only accepts the result when its syllable count matches the word's
    character count (sanity check against ToJyutping segmentation quirks
    e.g. splitting on an internal word boundary it thinks it sees).
    """
    import ToJyutping

    overrides: Dict[str, str] = {}
    skipped = 0
    for word in tied_words:
        gjt = ToJyutping.get_jyutping_text(word)
        if len(gjt.split()) == len(word):
            overrides[word] = gjt
        else:
            skipped += 1

    print(
        f"[tojyutping] resolved {len(overrides):,}/{len(tied_words):,} tied "
        f"rime-cantonese readings via get_jyutping_text() "
        f"({skipped:,} skipped — syllable/char count mismatch)"
    )
    return overrides


def build_candidates(
    word_entries: Dict[str, str],
    rime_readings: Dict[str, List[str]],
    tojyutping_candidates: Dict[str, List[str]],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Merge candidate-reading sources into the sparse Candidates API sidecar
    (Phase 7b-2). Only keys with 2+ distinct known readings are included —
    most dictionary entries have exactly one reading and need no row here.

    Priority:
    - ToJyutping's own rank-ordered candidate list wins outright when present
      — it reflects that package's own context-aware ranking, which is more
      trustworthy than our local tie-break heuristics (see resolve_tied_readings).
    - Otherwise, fall back to rime-cantonese's raw tied readings, with the
      winning reading already chosen for word_entries (by resolve_tied_readings
      or plain first-occurrence) moved to the front.

    Returns:
        candidates : dict[key -> "reading1|reading2|..."] ready for write_bin().
        confidence : dict[key -> "ranked" | "tied"] (Phase 7b-3, issue #12) —
            "ranked" when ToJyutping's own context-aware ranking produced the
            order (a real preference signal); "tied" when the order instead
            came from rime-cantonese's raw arbitrary tie-break (no real
            signal — see resolve_tied_readings). Neither is a numeric
            probability: no bundled source computes one (ToJyutping's trie
            stores an ordered list, not weights; rime ties are arbitrary
            first-occurrence order) — see CHANGELOG for the research behind
            this categorical-only design.
    """
    result: Dict[str, List[str]] = {}
    confidence: Dict[str, str] = {}

    for word, candidates in tojyutping_candidates.items():
        result[word] = candidates
        confidence[word] = "ranked"

    for word, readings in rime_readings.items():
        if word in result:
            continue  # ToJyutping's ranking already covers this key
        distinct: List[str] = list(dict.fromkeys(readings))  # dedupe, preserve order
        winner = word_entries.get(word)
        if winner is not None:
            if winner in distinct:
                distinct.remove(winner)
            distinct.insert(0, winner)
        if len(distinct) > 1:
            result[word] = distinct
            confidence[word] = "tied"

    candidates_out = {word: "|".join(c) for word, c in result.items()}
    return candidates_out, confidence


# ---------------------------------------------------------------------------
# Segmentation-shadow pruning (2026-07-21)
# ---------------------------------------------------------------------------

# Must mirror MAX_WORD_CHARS in src/segment.rs.
SEGMENT_MAX_WORD_CHARS = 10


def _solo_char_reading(char: str, word_entries: Dict[str, str], char_entries: Dict[str, str]) -> str:
    """
    Mirrors g2p.rs's `token_to_jyutping` resolution for a single orphaned
    CJK character reaching the segmenter as its own token: word_dict is
    checked BEFORE char_dict (word_entries legitimately contains many
    single-char keys, e.g. from ToJyutping's trie).
    """
    if char in word_entries:
        return word_entries[char]
    return char_entries.get(char, char)


def _segment_greedy(text: str, word_dict: Dict[str, str], max_len: int = SEGMENT_MAX_WORD_CHARS) -> List[str]:
    """Pure-Python mirror of segment.rs's segment_cjk(): greedy leftmost
    longest-prefix-match over `word_dict`, one CJK run at a time."""
    tokens: List[str] = []
    i, n = 0, len(text)
    while i < n:
        match = None
        for length in range(min(max_len, n - i), 0, -1):
            cand = text[i : i + length]
            if cand in word_dict:
                match = cand
                break
        if match is None:
            match = text[i]
        tokens.append(match)
        i += len(match)
    return tokens


def _reconstruct_reading(
    text: str,
    word_dict: Dict[str, str],
    word_entries: Dict[str, str],
    char_entries: Dict[str, str],
) -> str:
    """Mirrors token_to_jyutping(): segment `text` against `word_dict`, then
    resolve each resulting token the same way the Rust runtime would."""
    parts: List[str] = []
    for tok in _segment_greedy(text, word_dict):
        if tok in word_dict:
            parts.append(word_dict[tok])
        elif len(tok) == 1:
            parts.append(_solo_char_reading(tok, word_entries, char_entries))
        else:
            # Multi-char orphan — architecturally rare, mirrors g2p.rs's
            # per-character fallback loop.
            parts.append(" ".join(_solo_char_reading(c, word_entries, char_entries) for c in tok))
    return " ".join(parts)


def prune_compositional_word_entries(
    word_entries: Dict[str, str],
    char_entries: Dict[str, str],
    protected_keys: Set[str],
) -> Tuple[Dict[str, str], Set[str]]:
    """
    Remove word_entries whose presence in the SEGMENTATION dict conveys no
    G2P information beyond plain character-by-character fallback, but which
    actively cause the greedy longest-match segmenter to shadow real
    multi-char words starting mid-string.

    Root cause: rime-cantonese's words.dict.yaml is an IME phrase-completion
    list, not a pure lexicon — a large fraction of its entries are "purely
    compositional" (e.g. "我瞓" = "ngo5 fan3", exactly char_entries['我'] +
    char_entries['瞓']). Left in the segmentation dict, these entries still
    resolve correctly when matched on their own, but their PRESENCE greedily
    consumes a prefix of the string, so a real compound starting at the
    swallowed character (e.g. "瞓覺" right after "我") never gets a chance to
    match — the orphaned trailing character falls into ambiguous
    "ranked"-confidence char fallback instead (e.g. 覺 → gok3 instead of the
    correct gaau3). See CHANGELOG's 瞓覺 case (2026-07-21) for the case that
    surfaced this via HKCanCor corpus review.

    Safety check (per entry, not a heuristic): an entry W is only pruned if
    — after removing ALL prune candidates from the segmentation dict —
    re-segmenting the bare string W and resolving each resulting token
    reconstructs EXACTLY W's original reading. This runs to a fixed point:
    any entry whose own reading would change if pruned is kept back, and the
    whole candidate set is re-checked against the resulting (less-aggressive)
    dict until no further entries need to be kept back (empirically converges
    in 1-2 passes over the full bundled dictionary).

    `protected_keys` (oral_hk.tsv / variant_words.tsv / tone_sandhi_words.tsv)
    are never pruned regardless of this test — those are final, hand-curated
    decisions, not raw rime/tojyutping data.
    """
    candidates: Set[str] = set()
    for word, reading in word_entries.items():
        if len(word) < 2 or word in protected_keys:
            continue
        syllables = reading.split()
        if len(syllables) != len(word):
            continue
        compositional = [_solo_char_reading(c, word_entries, char_entries) for c in word]
        if compositional == syllables:
            candidates.add(word)

    prune_set = set(candidates)
    for _ in range(5):
        pruned_dict = {w: r for w, r in word_entries.items() if w not in prune_set}
        keep_back = {
            w
            for w in prune_set
            if _reconstruct_reading(w, pruned_dict, word_entries, char_entries) != word_entries[w]
        }
        if not keep_back:
            break
        prune_set -= keep_back

    pruned_word_entries = {w: r for w, r in word_entries.items() if w not in prune_set}
    return pruned_word_entries, prune_set


# ---------------------------------------------------------------------------
# Binary writer
# ---------------------------------------------------------------------------

def write_bin(entries: Dict[str, str], out_path: Path) -> int:
    """
    Write entries to a CJYP v1 binary file.
    Entries are sorted lexicographically by UTF-8 key bytes before writing.
    Returns the total number of bytes written.
    """
    # Sort by raw UTF-8 bytes of the key
    sorted_pairs: List[Tuple[bytes, bytes]] = sorted(
        ((k.encode("utf-8"), v.encode("utf-8")) for k, v in entries.items()),
        key=lambda pair: pair[0],
    )

    # Build string pool and entry records in a single pass
    pool = bytearray()
    entry_records: List[Tuple[int, int, int, int]] = []

    for key_bytes, val_bytes in sorted_pairs:
        key_start = len(pool)
        pool.extend(key_bytes)
        val_start = len(pool)
        pool.extend(val_bytes)
        entry_records.append((key_start, len(key_bytes), val_start, len(val_bytes)))

    entry_count = len(entry_records)
    pool_size = len(pool)

    # Pack header (16 bytes)
    header = struct.pack(HEADER_FMT, MAGIC, VERSION, entry_count, pool_size)

    # Pack entry table (entry_count * 12 bytes)
    entry_table = bytearray()
    for key_start, key_len, val_start, val_len in entry_records:
        entry_table.extend(struct.pack(ENTRY_FMT, key_start, key_len, val_start, val_len))

    # Write atomically by writing all at once
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(header)
        fh.write(entry_table)
        fh.write(pool)

    return len(header) + len(entry_table) + len(pool)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_bin(path: Path, expected_count: int) -> None:
    """Quick sanity check: read header and verify entry_count and magic."""
    with open(path, "rb") as fh:
        raw_header = fh.read(16)
    magic, version, entry_count, pool_size = struct.unpack(HEADER_FMT, raw_header)
    assert magic == MAGIC, f"Bad magic in {path.name}: {magic!r}"
    assert version == VERSION, f"Bad version in {path.name}: {version}"
    assert entry_count == expected_count, (
        f"Entry count mismatch in {path.name}: "
        f"got {entry_count}, expected {expected_count}"
    )
    print(
        f"[validate]  {path.name}: magic=OK version={version} "
        f"entries={entry_count:,} pool={pool_size:,}B"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("canto-g2p  build_dict.py")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Step 1: Load oral_hk.tsv  (highest priority)
    # ------------------------------------------------------------------
    oral_dict = load_oral_hk(ORAL_HK_TSV)

    # ------------------------------------------------------------------
    # Step 2: Load rime-cantonese YAML files
    # ------------------------------------------------------------------
    rime_all, rime_chars, rime_tied, rime_readings = load_rime_cantonese(RIME_FILES)

    # ------------------------------------------------------------------
    # Step 3: Load Unihan (lowest priority, single-char fallback)
    # ------------------------------------------------------------------
    unihan_dict = load_unihan(UNIHAN_READINGS)

    # ------------------------------------------------------------------
    # Step 3b: Load ToJyutping trie (build-time-only dep, BSD-2-Clause)
    #   Rank-0 reading from CanCLID's curated trie; trusted over rime-
    #   cantonese's raw first-occurrence pick for shared keys.
    # ------------------------------------------------------------------
    tojyutping_all, tojyutping_chars, tojyutping_candidates, tojyutping_char_candidates = (
        load_tojyutping()
    )

    # ------------------------------------------------------------------
    # Step 3c: Resolve rime's arbitrary tie-breaks via ToJyutping's own
    #   segmentation (get_jyutping_text), not just exact trie-node hits.
    # ------------------------------------------------------------------
    tied_overrides = resolve_tied_readings(rime_tied)

    # ------------------------------------------------------------------
    # Step 4: Build word_entries
    #   Priority: oral_dict > tied_overrides > tojyutping_all > rime_all
    #   Apply in ascending priority so higher-priority layers overwrite.
    # ------------------------------------------------------------------
    word_entries: Dict[str, str] = {}
    word_entries.update(rime_all)            # lowest priority
    word_entries.update(tojyutping_all)      # overrides rime on shared keys; adds new keys
    word_entries.update(tied_overrides)      # re-disambiguates rime ties tojyutping_all missed
    word_entries.update(oral_dict)           # oral overrides everything

    # Full-coverage source tag per word_entries key (issue #13) — mirrors the
    # exact same priority chain above, one entry per word_entries key.
    word_source: Dict[str, str] = {}
    for w in rime_all:
        word_source[w] = "rime"
    for w in tojyutping_all:
        word_source[w] = "tojyutping"
    for w in tied_overrides:
        word_source[w] = "tojyutping_tiebreak"
    for w in oral_dict:
        word_source[w] = "oral_hk"

    # ------------------------------------------------------------------
    # Step 4b: Resolve variant_words.tsv aliases (借音字, v2.1.0)
    #   Highest priority — corrects char-fallback readings for common
    #   phonetic-loan miswritings. Copies the canonical spelling's already-
    #   resolved jyutping verbatim, so it never drifts out of sync.
    # ------------------------------------------------------------------
    variant_dict = load_variant_words(VARIANT_WORDS_TSV)
    for variant, canonical in variant_dict.items():
        if canonical not in word_entries:
            raise SystemExit(
                f"[ERROR] variant_words.tsv: canonical spelling {canonical!r} "
                f"(for variant {variant!r}) not found in word_entries — "
                f"it must already resolve via rime/tojyutping/oral_hk"
            )
        word_entries[variant] = word_entries[canonical]
        word_source[variant] = "variant_alias"

    # ------------------------------------------------------------------
    # Step 4c: Resolve tone_sandhi_words.tsv (變調, HKCanCor-verified, v2.2.0)
    #   Highest priority — word-level only (never touches char_entries):
    #   these words' correct spoken tone differs from the citation tone our
    #   char fallback would produce, but the underlying characters are
    #   polysemous enough elsewhere that a char-level override would be
    #   wrong (e.g. 年/籌/聞/類 keep their citation reading in other words).
    # ------------------------------------------------------------------
    tone_sandhi_dict = load_oral_hk(TONE_SANDHI_WORDS_TSV, tag="tone_sandhi")
    for word, jyutping in tone_sandhi_dict.items():
        word_entries[word] = jyutping
        word_source[word] = "hkcancor_verified"

    # ------------------------------------------------------------------
    # Step 5: Build char_entries (single chars only)
    #   Priority: oral > tojyutping_chars > rime_chars > unihan
    #   Apply in ascending priority so higher-priority layers overwrite.
    # ------------------------------------------------------------------
    char_entries: Dict[str, str] = {}
    char_entries.update(unihan_dict)          # lowest priority
    char_entries.update(rime_chars)           # rime overrides unihan
    char_entries.update(tojyutping_chars)     # tojyutping overrides rime_chars
    for word, jyut in oral_dict.items():      # oral overrides everything
        if len(word) == 1:
            char_entries[word] = jyut

    # Full-coverage source tag per char_entries key (issue #13) — mirrors the
    # exact same priority chain above.
    char_source: Dict[str, str] = {}
    for c in unihan_dict:
        char_source[c] = "unihan"
    for c in rime_chars:
        char_source[c] = "rime"
    for c in tojyutping_chars:
        char_source[c] = "tojyutping"
    for word in oral_dict:
        if len(word) == 1:
            char_source[word] = "oral_hk"

    # ------------------------------------------------------------------
    # Step 5a: Prune segmentation-shadow entries (2026-07-21)
    #   Purely-compositional rime/tojyutping word entries (their reading ==
    #   plain char-by-char concatenation) convey zero G2P information but
    #   greedily shadow real compounds starting mid-string (e.g. "我瞓"
    #   blocking "瞓覺" from ever matching, orphaning "覺" into ambiguous
    #   ranked char fallback → wrong gok3 instead of gaau3). Removing a
    #   pruned entry never changes its OWN reading — see
    #   prune_compositional_word_entries()'s fixed-point safety proof.
    #   oral_hk/variant_alias/tone_sandhi entries are always protected, and
    #   so is any entry with genuine word-level candidate ambiguity (rime's
    #   own tied readings, or ToJyutping's ranked candidates) — e.g. "正經"
    #   (zing3 ging1 / zing1 ging1) must keep surfacing that word-specific
    #   tie via the Candidates API, not collapse into an unrelated per-char
    #   ambiguity for "正" alone (zing3/zeng3/zing1, most of which don't even
    #   apply to this word).
    # ------------------------------------------------------------------
    ambiguous_word_keys = set(tojyutping_candidates) | {
        w for w, r in rime_readings.items() if len(w) >= 2 and len(set(r)) > 1
    }
    protected_keys = (
        set(oral_dict) | set(variant_dict) | set(tone_sandhi_dict) | ambiguous_word_keys
    )
    word_entries, pruned_word_keys = prune_compositional_word_entries(
        word_entries, char_entries, protected_keys
    )
    for word in pruned_word_keys:
        word_source.pop(word, None)

    # ------------------------------------------------------------------
    # Step 5b: Build Candidates API sidecars (Phase 7b-2) — sparse, only
    #   keys with 2+ distinct known readings. oral_hk/variant_alias/
    #   tone_sandhi entries are excluded entirely: a hand-curated override
    #   is a final decision, not ambiguity to surface.
    # ------------------------------------------------------------------
    word_candidates, word_candidates_confidence = build_candidates(
        word_entries, rime_readings, tojyutping_candidates
    )
    for word in list(oral_dict) + list(tone_sandhi_dict) + list(pruned_word_keys):
        word_candidates.pop(word, None)
        word_candidates_confidence.pop(word, None)

    rime_char_readings = {w: r for w, r in rime_readings.items() if len(w) == 1}
    char_candidates, char_candidates_confidence = build_candidates(
        char_entries, rime_char_readings, tojyutping_char_candidates
    )
    for word in oral_dict:
        if len(word) == 1:
            char_candidates.pop(word, None)
            char_candidates_confidence.pop(word, None)

    # Sanity check: word_source/char_source must cover every key in
    # word_entries/char_entries (issue #13) — both are built via the exact
    # same priority chain, so a mismatch means the chains drifted apart.
    assert word_source.keys() == word_entries.keys(), (
        f"word_source coverage mismatch: {len(word_source):,} vs "
        f"{len(word_entries):,} word_entries"
    )
    assert char_source.keys() == char_entries.keys(), (
        f"char_source coverage mismatch: {len(char_source):,} vs "
        f"{len(char_entries):,} char_entries"
    )

    # ------------------------------------------------------------------
    # Step 6: Write binary files
    # ------------------------------------------------------------------
    print()
    print(f"[build]     Writing {OUT_WORD_BIN} ...")
    word_bytes = write_bin(word_entries, OUT_WORD_BIN)
    print(f"[build]     Writing {OUT_CHAR_BIN} ...")
    char_bytes = write_bin(char_entries, OUT_CHAR_BIN)
    print(f"[build]     Writing {OUT_WORD_CANDIDATES_BIN} ...")
    word_candidates_bytes = write_bin(word_candidates, OUT_WORD_CANDIDATES_BIN)
    print(f"[build]     Writing {OUT_CHAR_CANDIDATES_BIN} ...")
    char_candidates_bytes = write_bin(char_candidates, OUT_CHAR_CANDIDATES_BIN)
    print(f"[build]     Writing {OUT_WORD_CANDIDATES_CONFIDENCE_BIN} ...")
    word_confidence_bytes = write_bin(word_candidates_confidence, OUT_WORD_CANDIDATES_CONFIDENCE_BIN)
    print(f"[build]     Writing {OUT_CHAR_CANDIDATES_CONFIDENCE_BIN} ...")
    char_confidence_bytes = write_bin(char_candidates_confidence, OUT_CHAR_CANDIDATES_CONFIDENCE_BIN)
    print(f"[build]     Writing {OUT_WORD_SOURCE_BIN} ...")
    word_source_bytes = write_bin(word_source, OUT_WORD_SOURCE_BIN)
    print(f"[build]     Writing {OUT_CHAR_SOURCE_BIN} ...")
    char_source_bytes = write_bin(char_source, OUT_CHAR_SOURCE_BIN)

    # ------------------------------------------------------------------
    # Validate output files
    # ------------------------------------------------------------------
    print()
    validate_bin(OUT_WORD_BIN, len(word_entries))
    validate_bin(OUT_CHAR_BIN, len(char_entries))
    validate_bin(OUT_WORD_CANDIDATES_BIN, len(word_candidates))
    validate_bin(OUT_CHAR_CANDIDATES_BIN, len(char_candidates))
    validate_bin(OUT_WORD_CANDIDATES_CONFIDENCE_BIN, len(word_candidates_confidence))
    validate_bin(OUT_CHAR_CANDIDATES_CONFIDENCE_BIN, len(char_candidates_confidence))
    validate_bin(OUT_WORD_SOURCE_BIN, len(word_source))
    validate_bin(OUT_CHAR_SOURCE_BIN, len(char_source))

    # ------------------------------------------------------------------
    # Final stats
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("Build complete — summary")
    print("=" * 60)
    print(f"  word.bin            : {len(word_entries):>8,} entries   {word_bytes:>10,} bytes  ({word_bytes / 1024:.1f} KiB)")
    print(f"  char.bin            : {len(char_entries):>8,} entries   {char_bytes:>10,} bytes  ({char_bytes / 1024:.1f} KiB)")
    print(f"  word_candidates.bin : {len(word_candidates):>8,} entries   {word_candidates_bytes:>10,} bytes  ({word_candidates_bytes / 1024:.1f} KiB)")
    print(f"  char_candidates.bin : {len(char_candidates):>8,} entries   {char_candidates_bytes:>10,} bytes  ({char_candidates_bytes / 1024:.1f} KiB)")
    print(f"  word_candidates_confidence.bin : {len(word_candidates_confidence):>8,} entries   {word_confidence_bytes:>10,} bytes  ({word_confidence_bytes / 1024:.1f} KiB)")
    print(f"  char_candidates_confidence.bin : {len(char_candidates_confidence):>8,} entries   {char_confidence_bytes:>10,} bytes  ({char_confidence_bytes / 1024:.1f} KiB)")
    print(f"  word_source.bin     : {len(word_source):>8,} entries   {word_source_bytes:>10,} bytes  ({word_source_bytes / 1024:.1f} KiB)")
    print(f"  char_source.bin     : {len(char_source):>8,} entries   {char_source_bytes:>10,} bytes  ({char_source_bytes / 1024:.1f} KiB)")
    total = (
        word_bytes + char_bytes + word_candidates_bytes + char_candidates_bytes
        + word_confidence_bytes + char_confidence_bytes + word_source_bytes + char_source_bytes
    )
    print(f"  total               :                     {total:>10,} bytes  ({total / 1024:.1f} KiB)")
    print()
    print(f"  oral_hk entries          : {len(oral_dict):,}")
    print(f"  variant_words (aliases)  : {len(variant_dict):,}")
    print(f"  tone_sandhi_words        : {len(tone_sandhi_dict):,}")
    print(f"  pruned segmentation-shadow entries : {len(pruned_word_keys):,}")
    print(f"  rime-cantonese (all)     : {len(rime_all):,}")
    print(f"  rime-cantonese (chars)   : {len(rime_chars):,}")
    print(f"  tojyutping (all)         : {len(tojyutping_all):,}")
    print(f"  tojyutping (chars)       : {len(tojyutping_chars):,}")
    print(f"  rime tied (arbitrary)    : {len(rime_tied):,}")
    print(f"  tied resolved via gjt()  : {len(tied_overrides):,}")
    print(f"  unihan kCantonese        : {len(unihan_dict):,}")
    print(f"  word candidates (2+)     : {len(word_candidates):,}")
    print(f"  char candidates (2+)     : {len(char_candidates):,}")
    word_ranked = sum(1 for v in word_candidates_confidence.values() if v == "ranked")
    char_ranked = sum(1 for v in char_candidates_confidence.values() if v == "ranked")
    print(f"  word candidates ranked/tied : {word_ranked:,} / {len(word_candidates_confidence) - word_ranked:,}")
    print(f"  char candidates ranked/tied : {char_ranked:,} / {len(char_candidates_confidence) - char_ranked:,}")
    from collections import Counter
    word_source_counts = Counter(word_source.values())
    char_source_counts = Counter(char_source.values())
    print(f"  word source breakdown   : {dict(word_source_counts)}")
    print(f"  char source breakdown   : {dict(char_source_counts)}")
    print("=" * 60)

    # Copy cmudict.dict into package data for bundling
    if CMUDICT_SRC.exists():
        import shutil
        shutil.copy2(CMUDICT_SRC, CMUDICT_DST)
        print(f"OK  Copied cmudict.dict → {CMUDICT_DST.relative_to(REPO_ROOT)}")
    else:
        print("WARN  cmudict.dict not found — run fetch_data.py first", file=sys.stderr)


if __name__ == "__main__":
    main()
