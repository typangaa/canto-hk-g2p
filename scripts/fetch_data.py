#!/usr/bin/env python3
"""
Phase 1 data fetch — downloads rime-cantonese (CC-BY-4.0) and Unihan kCantonese
(Unicode License v3) into data/raw/, then writes data/SOURCES.md.

Run from repo root:
    python3 scripts/fetch_data.py

No external deps — uses stdlib urllib only.
"""
import hashlib
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# ── Pinned sources ──────────────────────────────────────────────────────────

RIME_COMMIT = "ec6ee73e8313"
RIME_DATE   = "2026-03-07"
RIME_BASE   = f"https://raw.githubusercontent.com/rime/rime-cantonese/{RIME_COMMIT}"

# CC-BY-4.0 files only — jyut6ping3.maps is ODbL (copyleft), excluded.
RIME_FILES = [
    "jyut6ping3.chars.dict.yaml",    # ~345 KB — single-char readings
    "jyut6ping3.words.dict.yaml",    # ~2.5 MB — word readings (main polyphone resolver)
    "jyut6ping3.phrase.dict.yaml",   # ~4.7 MB — phrase readings
    "jyut6ping3.lettered.dict.yaml", # ~23 KB  — mixed CJK+Latin entries
]

# Unicode Unihan — Unicode License v3 (permissive)
# Unihan_Readings.txt is packaged inside Unihan.zip at the latest/ path.
UNIHAN_ZIP_URL = "https://unicode.org/Public/UCD/latest/ucd/Unihan.zip"
UNIHAN_READING_FILE = "Unihan_Readings.txt"

# CMU Pronouncing Dictionary — BSD-2-Clause
CMUDICT_URL  = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
CMUDICT_DIR  = None  # set after DATA_RAW is defined below

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
DATA_RAW  = REPO_ROOT / "data" / "raw"
RIME_DIR  = DATA_RAW / "rime-cantonese"
UNIHAN_DIR = DATA_RAW / "unihan"
CMUDICT_DIR = DATA_RAW / "cmudict"

# ── Helpers ──────────────────────────────────────────────────────────────────

def download(url: str, dest: Path) -> str:
    """Download url → dest, show progress, return sha256 hex."""
    print(f"  fetching {dest.name} ...", end=" ", flush=True)
    tmp = dest.with_suffix(".tmp")
    h = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)
            h.update(chunk)
            total += len(chunk)
    tmp.rename(dest)
    print(f"{total / 1024:.0f} KB  sha256={h.hexdigest()[:16]}…")
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    RIME_DIR.mkdir(parents=True, exist_ok=True)
    UNIHAN_DIR.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}

    # ── 1. rime-cantonese ─────────────────────────────────────────────────
    print(f"\n[1/3] rime-cantonese  (commit {RIME_COMMIT}, CC-BY-4.0)")
    for fname in RIME_FILES:
        dest = RIME_DIR / fname
        if dest.exists():
            print(f"  {fname}  already present, skipping")
            checksums[fname] = sha256_file(dest)
        else:
            checksums[fname] = download(f"{RIME_BASE}/{fname}", dest)

    # ── 2. Unihan_Readings.txt (from Unihan.zip) ──────────────────────────
    print(f"\n[2/3] Unihan_Readings.txt  (Unicode License v3, via Unihan.zip)")
    unihan_dest = UNIHAN_DIR / "Unihan_Readings.txt"
    if unihan_dest.exists():
        print(f"  Unihan_Readings.txt  already present, skipping")
        checksums["Unihan_Readings.txt"] = sha256_file(unihan_dest)
    else:
        print(f"  fetching Unihan.zip ...", end=" ", flush=True)
        with urllib.request.urlopen(UNIHAN_ZIP_URL) as resp:
            zip_bytes = resp.read()
        print(f"{len(zip_bytes) / 1024**2:.1f} MB downloaded")
        print(f"  extracting {UNIHAN_READING_FILE} ...", end=" ", flush=True)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            data = zf.read(UNIHAN_READING_FILE)
        unihan_dest.write_bytes(data)
        h = hashlib.sha256(data).hexdigest()
        checksums["Unihan_Readings.txt"] = h
        print(f"{len(data) / 1024**2:.1f} MB  sha256={h[:16]}…")

    # Quick sanity: count kCantonese entries
    cant_count = sum(
        1 for line in open(unihan_dest, encoding="utf-8")
        if "\tkCantonese\t" in line
    )
    print(f"  kCantonese entries: {cant_count:,}")

    # ── 3. CMU Pronouncing Dictionary ─────────────────────────────────────
    CMUDICT_DIR.mkdir(parents=True, exist_ok=True)
    print("\n[3/3] CMU Pronouncing Dictionary  (BSD-2-Clause)")
    cmudict_dest = CMUDICT_DIR / "cmudict.dict"
    if cmudict_dest.exists():
        print("  cmudict.dict  already present, skipping")
        checksums["cmudict.dict"] = sha256_file(cmudict_dest)
    else:
        checksums["cmudict.dict"] = download(CMUDICT_URL, cmudict_dest)

    # ── 4. Write SOURCES.md ───────────────────────────────────────────────
    sources_path = REPO_ROOT / "data" / "SOURCES.md"
    lines = [
        "# Data sources\n",
        "Generated by `scripts/fetch_data.py`. Do not edit manually.\n",
        "\n",
        "## rime-cantonese\n",
        f"- Commit: `{RIME_COMMIT}` ({RIME_DATE})\n",
        "- License: CC-BY-4.0\n",
        "- Repo: https://github.com/rime/rime-cantonese\n",
        "- Files included (CC-BY-4.0 only; `jyut6ping3.maps` excluded — ODbL):\n",
    ]
    for fname in RIME_FILES:
        lines.append(f"  - `{fname}`  sha256={checksums[fname][:16]}…\n")

    lines += [
        "\n",
        "## Unihan Database\n",
        "- Version: latest (pinned by sha256 below)\n",
        "- License: Unicode License v3 (https://www.unicode.org/license.txt)\n",
        "- Source: https://unicode.org/charts/unihan.html\n",
        "- File: `Unihan_Readings.txt`  "
        f"sha256={checksums['Unihan_Readings.txt'][:16]}…\n",
        f"- kCantonese entries: {cant_count:,}\n",
        "\n",
        "## CMU Pronouncing Dictionary\n",
        "- Version: latest (from cmusphinx/cmudict master)\n",
        "- License: BSD 2-Clause\n",
        "- Source: https://github.com/cmusphinx/cmudict\n",
        "- Credit: Carnegie Mellon University Speech Group\n",
        f"- File: `cmudict.dict`  sha256={checksums.get('cmudict.dict', 'unknown')[:16]}…\n",
        "\n",
        "## Hand-curated\n",
        "- `data/oral_hk.tsv` — HK colloquial characters (~60 entries)\n",
        "- License: Apache-2.0 (same as canto-g2p)\n",
    ]
    sources_path.write_text("".join(lines), encoding="utf-8")
    print(f"\nOK  Wrote {sources_path.relative_to(REPO_ROOT)}")

    # ── 5. Summary ────────────────────────────────────────────────────────
    rime_total = sum((RIME_DIR / f).stat().st_size for f in RIME_FILES)
    unihan_size = unihan_dest.stat().st_size
    cmudict_size = cmudict_dest.stat().st_size
    print(f"\n{'─'*50}")
    print(f"rime-cantonese:  {rime_total / 1024**2:.1f} MB  ({len(RIME_FILES)} files)")
    print(f"Unihan:          {unihan_size / 1024**2:.1f} MB")
    print(f"cmudict:         {cmudict_size / 1024**2:.1f} MB")
    print(f"Total raw data:  {(rime_total + unihan_size + cmudict_size) / 1024**2:.1f} MB")
    print(f"{'─'*50}")
    print("Phase 1 data fetch complete. Next: run builder to generate .bin files.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
