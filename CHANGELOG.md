# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
