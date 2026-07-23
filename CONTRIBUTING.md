# Contributing to canto-hk-g2p

## Development setup

### Option A — uv (recommended)

```bash
# Prerequisites: Rust stable toolchain — https://rustup.rs/
# uv — https://docs.astral.sh/uv/getting-started/installation/

# 1. Clone
git clone https://github.com/typangaa/canto-hk-g2p.git
cd canto-hk-g2p

# 2. Fetch raw data sources (one-time, ~16 MB)
uv run python scripts/fetch_data.py

# 3. Build binary pronunciation dicts (output → python/canto_hk_g2p/data/)
uv run python scripts/build_dict.py

# 4. Build and install the Rust extension into the uv-managed venv
uv run --with maturin maturin develop --uv
```

### Option B — pip + maturin

```bash
pip install maturin pytest
python3 scripts/fetch_data.py
python3 scripts/build_dict.py
maturin develop --release
```

## Running tests

```bash
# Rust unit tests (168 tests)
cargo test

# Python integration tests (347 tests)
uv run --group dev pytest tests/ -v
# or: python3 -m pytest tests/ -v
```

All 515 tests must pass before submitting a pull request.

## Project structure

```
src/
  normalizer.rs     — text normaliser: numbers/dates/units/currency/fractions
  segment.rs        — CJK/Latin/Other run detection + longest-match segmenter
  g2p.rs            — word dict → Latin passthrough → char-by-char fallback
  pipeline.rs       — orchestrates all stages; Rayon parallel batch
  dict/lookup.rs    — mmap CJYP binary dict, O(log n) binary search
  lib.rs            — PyO3 bindings (Python API surface)
python/canto_hk_g2p/
  __init__.py       — public Pipeline class
  data/             — generated binary dicts (gitignored, bundled in wheel)
data/
  oral_hk.tsv       — hand-curated HK colloquial char/phrase overrides
  variant_words.tsv — 借音字 (phonetic-loan) aliases: miswriting → canonical word
  raw/              — downloaded source data (gitignored)
scripts/
  fetch_data.py     — download rime-cantonese + Unihan (pinned versions)
  build_dict.py     — build CJYP binary dicts → python/canto_hk_g2p/data/
  benchmark.py      — speed benchmark vs ToJyutping / PyCantonese
```

## Adding or updating dictionary entries

Edit `data/oral_hk.tsv` (tab-separated: `word<TAB>jyutping`). Supports both single
characters and multi-character phrases. This file has the highest priority and
overrides rime-cantonese and Unihan.

## Adding a 借音字 (phonetic-loan) alias

If you find a common miswriting that borrows a homophone character's sound
(e.g. 訓覺 for 瞓覺, 岩岩 for 啱啱) and produces the wrong reading, add a row to
`data/variant_words.tsv`: `variant_spelling<TAB>canonical_spelling`. The
canonical spelling must already resolve correctly (via rime-cantonese,
ToJyutping, or `oral_hk.tsv`) — `build_dict.py` copies its reading verbatim
and tags the variant with `source="variant_alias"`.

Do **not** add a case unless the canonical word's own reading is unambiguous
in real usage — e.g. 黎/嚟 was deliberately left out of the seed list because
both `lai4` and `lei4` are attested standard readings for 嚟 itself, so there
is no single "correct" reading to alias to.

Also check for **segmentation collisions** before adding a row: the variant
spelling must not be a prefix of some other real dictionary word starting
with the same character(s), or the longest-match segmenter will shadow that
real word. `個度` (for 嗰度) was tried and rejected this way — it collides
with `度數` inside `個度數` ("this reading/number"). Check with:

```bash
uv run python3 -c "
import sys; sys.path.insert(0, 'scripts')
from build_dict import load_tojyutping, load_rime_cantonese, RIME_FILES
tojyutping_all, *_ = load_tojyutping()
rime_all, *_ = load_rime_cantonese(RIME_FILES)
prefix = '個度'  # the variant spelling you're about to add
hits = [w for w in list(tojyutping_all) + list(rime_all) if w.startswith(prefix) and len(w) > len(prefix)]
print(hits or 'no collision')
"
```

After editing either file, rebuild and reinstall:

```bash
uv run python scripts/build_dict.py
uv run --with maturin maturin develop --uv
```

## Adding a 離合詞 (separable verb-object compound)

If a real compound word can have a Cantonese aspect marker (緊/咗/過/開)
inserted between its two syllables in natural speech (e.g. 瞓覺 → 瞓緊覺,
"sleeping") *and* that changes what reading its second syllable needs (瞓覺's
覺 is `gaau3`, not its own default `gok3`), add a row to
`data/separable_words.tsv`: `word<TAB>note` (the note is documentation only —
the reading is always read from the word's own `word.bin` entry at build
time, so it can never drift out of sync).

Requirements, checked by `build_dict.py` (raises `SystemExit` otherwise):
- the word must be exactly 2 characters (single-char verb + single-char
  noun only — longer separable compounds aren't supported yet)
- the word must already resolve correctly via rime-cantonese / ToJyutping /
  `oral_hk.tsv`

Only add an entry when it actually changes the outcome — if every syllable's
compound reading already matches its own default/solo reading, the
char-fallback path produces the right answer on its own and the whitelist
entry is a no-op. The aspect-marker list itself (緊/咗/過/開) is a fixed,
closed grammatical class hardcoded in `src/separable.rs` — it isn't meant to
grow via data changes.

After editing, rebuild and reinstall the same way as above.

## License compliance

All data sources must be permissive (MIT / Apache / CC-BY / Unicode License).
**Never add** entries from: rime-cantonese `.maps` (ODbL share-alike),
CC-Canto (CC-BY-SA), words.hk (proprietary), CantoDict (proprietary),
or any CC-BY-SA / copyleft source — these would require share-alike on derivative data.

See `data/SOURCES.md` for provenance of all bundled data.

## Submitting changes

1. Fork and create a feature branch.
2. Ensure `cargo test` and `pytest tests/` both pass with zero failures.
3. For data changes, run `python3 scripts/build_dict.py` and verify output.
4. Open a pull request describing the change and its motivation.
