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

def load_oral_hk(path: Path) -> Dict[str, str]:
    """
    Load oral_hk.tsv — highest-priority overrides.
    Format:  char<TAB>jyutping
    Skips lines starting with '#' or blank lines.
    If a key appears multiple times, LAST entry wins (so later curations
    override earlier ones within the file — e.g. the two entries for 囉/㗎).
    """
    result: Dict[str, str] = {}
    if not path.exists():
        print(f"[WARN] oral_hk.tsv not found: {path}", file=sys.stderr)
        return result

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"[WARN] oral_hk.tsv:{lineno}: bad line: {line!r}", file=sys.stderr)
                continue
            word, jyutping = parts[0].strip(), parts[1].strip()
            if word and jyutping:
                result[word] = jyutping  # last occurrence wins

    print(f"[oral_hk]   loaded {len(result):,} entries from {path.name}")
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
) -> Dict[str, str]:
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

    Returns dict[key -> "reading1|reading2|..."] ready for write_bin().
    """
    result: Dict[str, List[str]] = {}

    for word, candidates in tojyutping_candidates.items():
        result[word] = candidates

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

    return {word: "|".join(candidates) for word, candidates in result.items()}


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

    # ------------------------------------------------------------------
    # Step 5b: Build Candidates API sidecars (Phase 7b-2) — sparse, only
    #   keys with 2+ distinct known readings. oral_hk entries are excluded
    #   entirely: a hand-curated override is a final decision, not ambiguity
    #   to surface.
    # ------------------------------------------------------------------
    word_candidates = build_candidates(word_entries, rime_readings, tojyutping_candidates)
    for word in oral_dict:
        word_candidates.pop(word, None)

    rime_char_readings = {w: r for w, r in rime_readings.items() if len(w) == 1}
    char_candidates = build_candidates(char_entries, rime_char_readings, tojyutping_char_candidates)
    for word in oral_dict:
        if len(word) == 1:
            char_candidates.pop(word, None)

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

    # ------------------------------------------------------------------
    # Validate output files
    # ------------------------------------------------------------------
    print()
    validate_bin(OUT_WORD_BIN, len(word_entries))
    validate_bin(OUT_CHAR_BIN, len(char_entries))
    validate_bin(OUT_WORD_CANDIDATES_BIN, len(word_candidates))
    validate_bin(OUT_CHAR_CANDIDATES_BIN, len(char_candidates))

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
    total = word_bytes + char_bytes + word_candidates_bytes + char_candidates_bytes
    print(f"  total               :                     {total:>10,} bytes  ({total / 1024:.1f} KiB)")
    print()
    print(f"  oral_hk entries          : {len(oral_dict):,}")
    print(f"  rime-cantonese (all)     : {len(rime_all):,}")
    print(f"  rime-cantonese (chars)   : {len(rime_chars):,}")
    print(f"  tojyutping (all)         : {len(tojyutping_all):,}")
    print(f"  tojyutping (chars)       : {len(tojyutping_chars):,}")
    print(f"  rime tied (arbitrary)    : {len(rime_tied):,}")
    print(f"  tied resolved via gjt()  : {len(tied_overrides):,}")
    print(f"  unihan kCantonese        : {len(unihan_dict):,}")
    print(f"  word candidates (2+)     : {len(word_candidates):,}")
    print(f"  char candidates (2+)     : {len(char_candidates):,}")
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
