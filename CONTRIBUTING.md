# Contributing to canto-g2p

## Development setup

```bash
# Prerequisites: Rust stable, Python ≥ 3.8, maturin
pip install maturin pytest

# Fetch raw data sources (one-time, ~16 MB)
python3 scripts/fetch_data.py

# Build binary dicts
python3 scripts/build_dict.py

# Build and install development wheel
maturin build --release
pip install target/wheels/*.whl --force-reinstall
```

## Running tests

```bash
cargo test                    # 39 Rust unit tests
python3 -m pytest tests/ -v   # 53 Python integration tests
```

## Project structure

```
src/
  normalizer.rs   — text normalizer (numbers, dates, percent → Chinese chars)
  segment.rs      — CJK/Latin/Other run detection + longest-match segmenter
  g2p.rs          — word dict → passthrough → char-by-char fallback
  pipeline.rs     — orchestrates all stages; Rayon batch
  dict/lookup.rs  — mmap binary dict, O(log n) binary search
  lib.rs          — PyO3 bindings
data/
  oral_hk.tsv     — hand-curated HK colloquial char overrides
scripts/
  fetch_data.py   — download rime-cantonese + Unihan (pinned versions)
  build_dict.py   — build CJYP binary dicts from raw sources
  benchmark.py    — speed benchmark vs ToJyutping / PyCantonese
```

## Adding or updating dictionary entries

Edit `data/oral_hk.tsv` (tab-separated: `char<TAB>jyutping`). This file has the
highest priority and overrides rime-cantonese and Unihan for single characters.
After editing, rebuild the binary dicts and reinstall the wheel:

```bash
python3 scripts/build_dict.py
maturin build --release && pip install target/wheels/*.whl --force-reinstall
```

## License compliance

All data sources must be permissive (MIT / Apache / CC-BY / Unicode License).
**Never add** entries sourced from: rime-cantonese `.maps` (ODbL),
CC-Canto (CC-BY-SA), words.hk (proprietary), CantoDict (proprietary),
or any CC-BY-SA / copyleft source — these would require share-alike on derivative data.

## Submitting changes

1. Fork and create a feature branch.
2. Ensure `cargo test` and `pytest tests/` both pass with zero failures.
3. For data changes, run `python3 scripts/build_dict.py` and commit updated `.bin` files.
4. Open a pull request describing the change and its motivation.
