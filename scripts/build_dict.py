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
from typing import Dict, List, Tuple

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
    RAW_DIR / "rime-cantonese" / "jyut6ping3.phrase.dict.yaml",
    RAW_DIR / "rime-cantonese" / "jyut6ping3.lettered.dict.yaml",
]

UNIHAN_READINGS = RAW_DIR / "unihan" / "Unihan_Readings.txt"

OUT_WORD_BIN = DATA_DIR / "word.bin"
OUT_CHAR_BIN = DATA_DIR / "char.bin"

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


def load_rime_cantonese(paths: List[Path]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load rime-cantonese dict YAML files.

    Returns:
        rime_all   : dict[word -> jyutping]  (all words, single- and multi-char)
        rime_chars : dict[char -> jyutping]  (single-char entries only)

    Deduplication rules:
    - Same key in an EARLIER file wins over a LATER file.
    - Within a file, keep the entry with the HIGHEST weight percentage.
      If no weights are given, keep the FIRST occurrence (weight stays -1).
    - We overwrite only when the new candidate weight is strictly greater.
    """
    # Tracks the current best (jyutping, weight) for each key across all files.
    best_all: Dict[str, Tuple[str, int]] = {}
    best_chars: Dict[str, Tuple[str, int]] = {}

    for path in paths:
        if not path.exists():
            print(f"[WARN] rime file not found: {path}", file=sys.stderr)
            continue

        in_data = False  # True after we see the `...` separator
        file_entries = 0

        # Collect per-file best entries before merging (so earlier files lock keys)
        file_best: Dict[str, Tuple[str, int]] = {}

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
                    file_entries += 1
                else:
                    _, existing_weight = file_best[word]
                    if weight > existing_weight:
                        file_best[word] = (jyutping, weight)

        # Merge file_best into global dicts — earlier files already won
        new_from_file = 0
        for word, (jyut, w) in file_best.items():
            is_single = len(word) == 1

            if word not in best_all:
                best_all[word] = (jyut, w)
                new_from_file += 1
            # Keys already in best_all come from an earlier file — do not overwrite

            if is_single and word not in best_chars:
                best_chars[word] = (jyut, w)

        print(
            f"[rime]      {path.name}: {file_entries:,} unique entries in file, "
            f"{new_from_file:,} new added to global dict"
        )

    rime_all = {k: v[0] for k, v in best_all.items()}
    rime_chars = {k: v[0] for k, v in best_chars.items()}
    return rime_all, rime_chars


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
    rime_all, rime_chars = load_rime_cantonese(RIME_FILES)

    # ------------------------------------------------------------------
    # Step 3: Load Unihan (lowest priority, single-char fallback)
    # ------------------------------------------------------------------
    unihan_dict = load_unihan(UNIHAN_READINGS)

    # ------------------------------------------------------------------
    # Step 4: Build word_entries
    #   Priority: oral_dict > rime_all
    #   Start from rime (all words), then overlay oral overrides.
    # ------------------------------------------------------------------
    word_entries: Dict[str, str] = {}
    word_entries.update(rime_all)
    word_entries.update(oral_dict)   # oral overrides rime for any shared keys

    # ------------------------------------------------------------------
    # Step 5: Build char_entries (single chars only)
    #   Priority: oral > rime_chars > unihan
    #   Apply in ascending priority so higher-priority layers overwrite.
    # ------------------------------------------------------------------
    char_entries: Dict[str, str] = {}
    char_entries.update(unihan_dict)          # lowest priority
    char_entries.update(rime_chars)           # rime overrides unihan
    for word, jyut in oral_dict.items():      # oral overrides everything
        if len(word) == 1:
            char_entries[word] = jyut

    # ------------------------------------------------------------------
    # Step 6: Write binary files
    # ------------------------------------------------------------------
    print()
    print(f"[build]     Writing {OUT_WORD_BIN} ...")
    word_bytes = write_bin(word_entries, OUT_WORD_BIN)
    print(f"[build]     Writing {OUT_CHAR_BIN} ...")
    char_bytes = write_bin(char_entries, OUT_CHAR_BIN)

    # ------------------------------------------------------------------
    # Validate output files
    # ------------------------------------------------------------------
    print()
    validate_bin(OUT_WORD_BIN, len(word_entries))
    validate_bin(OUT_CHAR_BIN, len(char_entries))

    # ------------------------------------------------------------------
    # Final stats
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("Build complete — summary")
    print("=" * 60)
    print(f"  word.bin : {len(word_entries):>8,} entries   {word_bytes:>10,} bytes  ({word_bytes / 1024:.1f} KiB)")
    print(f"  char.bin : {len(char_entries):>8,} entries   {char_bytes:>10,} bytes  ({char_bytes / 1024:.1f} KiB)")
    print(f"  total    :                     {word_bytes + char_bytes:>10,} bytes  ({(word_bytes + char_bytes) / 1024:.1f} KiB)")
    print()
    print(f"  oral_hk entries          : {len(oral_dict):,}")
    print(f"  rime-cantonese (all)     : {len(rime_all):,}")
    print(f"  rime-cantonese (chars)   : {len(rime_chars):,}")
    print(f"  unihan kCantonese        : {len(unihan_dict):,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
