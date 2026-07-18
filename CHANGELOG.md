# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.0] — 2026-07-18

### Added

**Runtime override dictionary — `Pipeline(user_dict=...)`** (Phase 7b-1)
- New constructor parameter: `Pipeline(user_dict={"行": "hong4", "老世": "lou5 sai3"})`
  — maps a word or character to a space-separated Jyutping reading, layered on
  top of every bundled dictionary (rime-cantonese, ToJyutping, `oral_hk.tsv`)
  at the **highest** priority
- The override also participates in segmentation (not just lookup): a
  `user_dict` entry wins ties against an equal-length `word_dict` match, and a
  multi-char entry that doesn't exist in any bundled dict (e.g. `老世`) is not
  silently split apart by the longest-match segmenter before it ever reaches
  lookup
- Validated at construction time, not at `convert()` time: each value's
  space-separated syllable count must equal its key's character count, and
  every syllable must be well-formed Jyutping (checked via the existing
  `segment()` phonology API) — a malformed entry raises `ValueError`
  immediately instead of silently producing wrong output later
- **Known limitation**: an override only competes with `word_dict` at its own
  starting position in the segmenter's greedy longest-match scan. If a
  *longer* dictionary word starts one character earlier and happens to
  contain the override's key as a substring, that longer word wins and the
  override is shadowed (e.g. overriding `正經` has no effect inside `好正經`,
  because `好正經` is itself a 3-char rime-cantonese entry) — documented and
  covered by a regression test in `tests/test_user_dict.py`
- New Rust module `src/user_dict.rs` (`UserDict`) — plain `HashMap`-backed,
  mirrors `dict::Dict::longest_prefix_match`'s semantics so the two can be
  compared directly during segmentation; no `.bin` format change, no wheel
  size change
- 14 new Python tests (`tests/test_user_dict.py`) + 18 new Rust unit tests
  across `user_dict.rs`, `segment.rs`, and `g2p.rs`

This is the first half of the deferred "Candidates API" work (Phase 7b);
splitting it out because override is directly useful on its own (e.g. locking
a register-specific pronunciation for TTS training) and needs no `.bin`
format change, unlike the text-level `convert_candidates()` API still planned
for a future release.

[1.8.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.7.1...v1.8.0

## [1.7.1] — 2026-07-18

### Fixed

**Residual polyphone tie-break gap in `word.bin`**
- v1.7.0's `load_tojyutping()` only overrode a rime-cantonese tie when the word
  existed as an exact multi-char node in ToJyutping's trie — of the 1,428
  rime words with a genuine weight-tie (2+ equally-weighted, most often
  unweighted, candidate readings), only 692 had such a node; the remaining
  736 kept falling back to "first occurrence in file wins", which is not a
  real disambiguation signal (e.g. `正經` had both `zing1 ging1` and
  `zing3 ging1` at equal weight, and the wrong one was being picked)
- Added `scripts/build_dict.py::resolve_tied_readings()`, which calls
  ToJyutping's `get_jyutping_text()` — its own context-aware segmentation
  across the whole word, not a single exact-match lookup — for every tied
  rime word. Resolved 1,293 of 1,428 (the rest skipped on a syllable/char
  count sanity-check mismatch and keep their previous reading)
- `load_rime_cantonese()` now also returns the tied-word set so this can run;
  new merge priority: `oral_hk.tsv` > tied_overrides > ToJyutping trie >
  rime-cantonese (was: `oral_hk.tsv` > ToJyutping trie > rime-cantonese)
- Fixes e.g.: `一本正經` (`zing1`→`zing3`), `沉重` (`zung6`→`cung5`),
  `處理`/`處境` (`cyu2`→`cyu5`), `請問`/`請客` (`cing2`→`ceng2`),
  `廚師` (`ceoi4`→`cyu4`)
- 5 new gold-sentence regression tests added to `tests/test_polyphone_regression.py`

[1.7.1]: https://github.com/typangaa/canto-hk-g2p/compare/v1.7.0...v1.7.1

## [1.7.0] — 2026-07-18

### Fixed

**Polyphone (多音字) / 文白異讀 tie-breaking**
- Added [ToJyutping](https://github.com/CanCLID/ToJyutping) (CanCLID, BSD-2-Clause) as a
  **build-time-only** data source (not bundled in the wheel, not a runtime dependency) —
  used by `scripts/build_dict.py` to rank-order candidate readings and break ties that
  rime-cantonese leaves ambiguous (e.g. `行` had 6 equal-weight readings; `平`/`重`/`坐`/
  `識`/`近`/`聽`/`命`/`正` etc. all had un-ranked alternates)
- New merge priority: `word.bin` = rime-cantonese → ToJyutping → `oral_hk.tsv` (highest);
  `char.bin` = Unihan → rime-cantonese → ToJyutping → `oral_hk.tsv` (highest)
- Fixes previously-wrong output for common sentences, e.g.:
  - `行為不檢` : `haang4 wai4 ...` → `hang4 wai4 ...`
  - `呢件衫好平` : `... ping4` → `... peng4`
  - `個袋好重` : `... cung4` → `... cung5`
  - `自由行` : `... haang4` → `... hang4`
- Excludes 2 ToJyutping word entries (`二六`, `四六`) that carry tone-sandhi'd colloquial
  readings colliding with this library's own digit-by-digit number/year expansion, which
  requires citation tones only (see CLAUDE.md's locked "v1 skips tone sandhi" decision)
- 48 new gold-sentence regression tests in `tests/test_polyphone_regression.py`,
  cross-validated against ToJyutping's own output

### Removed
- `jyut6ping3.phrase.dict.yaml` dropped from the rime-cantonese fetch — the file lacks the
  `...` YAML front-matter separator our parser requires, so it was silently contributing
  0 entries in every build since v1.0.0 (no behavior change; just stopped downloading
  ~4.7 MB of unused data)

[1.7.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.6.0...v1.7.0

## [1.6.0] — 2026-07-13

### Added

**Jyutping phonological inventory + syllable segmentation API**
- `canto_hk_g2p.inventory()` — returns the authoritative LSHK Jyutping `Inventory` singleton:
  - `.onsets` — 19 onsets as a tuple, sorted longest-first (`ng`, `gw`, `kw` before single-char onsets)
  - `.rimes` — 61 rimes as a `frozenset`
  - `.tones` — `("1","2","3","4","5","6")`
  - `.syllabic` — `frozenset({"m","ng"})` — nasals that form a complete syllable on their own
- `canto_hk_g2p.segment(syllable)` — decomposes a Jyutping syllable string into a `Syllable(onset, rime, tone)` named tuple; returns `None` for invalid input
- `canto_hk_g2p.Syllable` / `canto_hk_g2p.Inventory` — public dataclass types (frozen, hashable)
- Pure Python implementation in `canto_hk_g2p.phonology` — no Rust changes, no new dependencies
- 45 new tests in `tests/test_phonology.py`

This makes `canto-hk-g2p` the single source of truth for the Jyutping phoneme inventory,
removing the need for downstream consumers (e.g. `canto-hk-tts`) to maintain their own copy.

[1.6.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.5.0...v1.6.0

## [1.5.0] — 2026-06-14

### Added

**IPA (International Phonetic Alphabet) output**
- `Pipeline.convert_ipa(text, tone="diacritic"|"number")` — converts Cantonese text to IPA
  - Cantonese tokens: Jyutping→IPA via complete LSHK phoneme mapping
  - English tokens: CMU Pronouncing Dictionary (BSD-2-Clause) → ARPAbet→IPA
  - Tone format: `"diacritic"` (default) uses IPA suprasegmentals ˥˧˥˧˨˩˩˧˨; `"number"` keeps digit suffix
- `canto_hk_g2p.ipa.jyutping_to_ipa(jyutping, tone)` — standalone utility for converting existing Jyutping strings to IPA
- `canto_hk_g2p.ipa.syllable_to_ipa(syllable, tone)` — single Jyutping syllable converter
- CMU Pronouncing Dictionary bundled in wheel (BSD-2-Clause, Carnegie Mellon University)
- Attribution added to NOTICE

[1.5.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.0.0...v1.5.0

## [1.0.0] — 2026-06-14

First public release. PyPI: `pip install canto-hk-g2p`.

### Added

**Core G2P**
- Rust core with PyO3/maturin Python bindings — zero runtime Python dependencies
- Word-level dictionary lookup with longest-match + word-frequency DP segmentation
- Per-character fallback using most-frequent reading for out-of-vocabulary characters
- English/Latin passthrough — mixed HK code-switching handled cleanly
  (`佢 send 咗 email 俾我` → `keoi5 send zo2 email bei2 ngo5`)
- Rayon parallel batch processing via `convert_batch()`
- Structured token-level output via `convert_detailed()` with language tags (`yue` / `en` / `punct`)

**Text normalizer** (Arabic digits → Cantonese spoken form)
- Year: `2026年` → `ji6 ling4 ji6 luk6 nin4`
- Date: `6月13日` → `luk6 jyut6 sap6 saam1 jat6`
- Percentage (integer + decimal): `50%` / `50.5%`
- Currency symbols: `HK$`, `¥`, `€`, `£`, `₩`, `￥`
- Currency codes: USD EUR GBP JPY CNY RMB AUD CAD KRW TWD SGD MYR THB
- Measurement units: `km/h` `m/s` `mph` `km` `cm` `mm` `mg` `kg` `mL` `°C` `°F` and more
- Fractions: `1/2` → 二分之一; `3/4` → 四分之三
- Scores: `3:1` → 三比一; `10:0` → 十比零
- Ordinal / floor / episode: `第3名` → 第三名; `3樓` → 三樓; `第3集` → 第三集
- Time and phone numbers

**Punctuation normalisation** (`punc_norm=True`, default on)
- `「」『』【】《》〈〉〔〕""''` → removed
- `…` / `……` / `...` → `。`
- `——` / `—` / `–` / `--` → `，`
- `·` `・` `•` → space; `～` `〜` → space; `、` → `，`
- Decorative symbols (★ ☆ □ ■ …) → removed

**Data sources** (permissive licenses only, bundled in wheel)
- rime-cantonese `jyut6ping3.dict/.chars/.words/.phrase` — CC-BY-4.0
- Unihan `kCantonese` — Unicode License v3
- Hand-curated HK colloquial characters (`data/oral_hk.tsv`) — Apache-2.0

**Distribution**
- Pre-built abi3 wheels (Python 3.8+) for Linux x86\_64 + aarch64, macOS x86\_64 + Apple Silicon, Windows x86\_64
- Apache-2.0 library license; data attribution in `NOTICE`
- 228 tests (115 Rust unit tests + 113 Python integration tests)

[1.0.0]: https://github.com/typangaa/canto-hk-g2p/compare/v0.0.0...v1.0.0
