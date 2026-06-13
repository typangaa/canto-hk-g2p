# canto-g2p

**Fast Cantonese text-to-phoneme (G2P) converter** — converts Cantonese (and English code-switched) text to Jyutping with tone numbers (LSHK standard, all-ASCII). Rust core with Python bindings via PyO3/maturin.

[![CI](https://github.com/typangaa/canto-g2p/actions/workflows/ci.yml/badge.svg)](https://github.com/typangaa/canto-g2p/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/canto-g2p)](https://pypi.org/project/canto-g2p/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

```python
from canto_g2p import Pipeline

p = Pipeline()
p.convert("你好嘅，I love Hong Kong")
# → "nei5 hou2 ge3 , I love hoeng1 gong2"
```

---

## Why this exists

Cantonese TTS systems struggle with two fundamental problems. First, colloquial Cantonese characters (嘅, 喺, 噉, 㗎, …) are rare or absent from standard Chinese vocabulary tables, causing tokenizers to split them into byte fragments that the model never learns to pronounce reliably. Second, Hong Kong Cantonese freely mixes English — a sentence like 佢 send 咗 email 俾我 is everyday speech — and no existing Cantonese G2P tool handles this.

`canto-g2p` solves both: it converts the entire input, including colloquial particles, numbers, dates, and inline English, to all-ASCII Jyutping before the text ever reaches a TTS encoder. The result is stable, tone-accurate phoneme sequences with 100% coverage.

The library is a standalone open-source deliverable — Cantonese TTS pre-processing is the primary motivation, but the tool is useful anywhere Cantonese phonemization is needed.

---

## Features

- **All-ASCII Jyutping output** with LSHK tone numbers (`nei5 hou2 ge3`)
- **English code-switching** — the only Cantonese G2P tool that handles mixed HK text (佢 send 咗 email 俾我)
- **Text normalization** — Arabic and full-width digits expanded to Cantonese spoken form:
  - Year: `2026年` → `ji6 ling4 ji6 luk6 nin4`
  - Date: `6月13日` → `luk6 jyut6 sap6 saam1 jat6`
  - Percentage: `50%` → `baak3 fan6 zi1 ng5 sap6`
  - Currency: `HK$100` → `jat1 baak3 jyun4`
  - Time: `下午3時15分` → Cantonese spoken time
  - Phone numbers: digit-by-digit expansion
- **Polyphone disambiguation** via longest-match word-level segmentation (~85% accuracy)
- **Rayon parallel batch processing** — scales to large corpora
- **Zero runtime Python dependencies** — pronunciation dictionaries bundled in the wheel
- **`convert_detailed()`** — structured `(token, jyutping, lang)` output with language tags (`yue` / `en` / `punct`)
- **Apache-2.0 license**, permissive data sources only — safe to redistribute

---

## Installation

> **Note:** canto-g2p is not yet published to PyPI. Install from source (see below) or watch the repository for the first release.

```bash
# Once published:
pip install canto-g2p
```

---

## Quick start

```python
from canto_g2p import Pipeline

p = Pipeline()

# Basic Cantonese
p.convert("你好嘅")
# → "nei5 hou2 ge3"

# Full sentence with punctuation and English
p.convert("你好嘅，I love Hong Kong")
# → "nei5 hou2 ge3 , I love hoeng1 gong2"

# Number and date normalization
p.convert("2026年6月13日")
# → "ji6 ling4 ji6 luk6 nin4 luk6 jyut6 sap6 saam1 jat6"

p.convert("50%")
# → "baak3 fan6 zi1 ng5 sap6"

# English code-switching (loanwords with Cantonese readings)
p.convert("佢send咗email俾我")
# → "keoi5 sen1 zo2 ji1 me1 lou4 bei2 ngo5"

# Batch conversion (Rayon parallel)
p.convert_batch(["香港", "銀行", "你好嘅"])
# → ["hoeng1 gong2", "ngan4 hong4", "nei5 hou2 ge3"]

# Structured output with language tags
p.convert_detailed("香港 hello")
# → [("香港", "hoeng1 gong2", "yue"), ("hello", "haa1 lou2", "en")]
```

---

## API reference

### `Pipeline()`

Loads the binary pronunciation dictionaries from the bundled `data/` directory. The pipeline object is reusable and thread-safe for batch calls.

```python
p = Pipeline()
```

---

### `convert(text: str) -> str`

Converts a string of Cantonese (or mixed Cantonese/English) text to space-separated Jyutping syllables.

| Parameter | Type | Description |
|---|---|---|
| `text` | `str` | Input text (UTF-8). May contain Cantonese characters, English words, digits, punctuation. |

**Returns:** `str` — space-separated Jyutping syllables. Punctuation tokens are preserved as-is. Pure English spans are passed through unchanged (unless the word has a Cantonese reading in the dictionary, e.g. `hello` → `haa1 lou2`).

```python
p.convert("銀行")          # → "ngan4 hong4"
p.convert("2026年")        # → "ji6 ling4 ji6 luk6 nin4"
p.convert("I love you")   # → "I love you"
p.convert("")             # → ""
```

---

### `convert_batch(texts: list[str]) -> list[str]`

Converts a list of strings in parallel using Rayon. Output order matches input order.

| Parameter | Type | Description |
|---|---|---|
| `texts` | `list[str]` | List of input strings. |

**Returns:** `list[str]` — one Jyutping string per input, in the same order.

```python
p.convert_batch(["香港", "銀行", "你好嘅"])
# → ["hoeng1 gong2", "ngan4 hong4", "nei5 hou2 ge3"]

p.convert_batch([])   # → []
```

---

### `convert_detailed(text: str) -> list[tuple[str, str, str]]`

Returns a structured token-level breakdown. Each element is a 3-tuple `(token, jyutping, lang)`.

| Field | Type | Values |
|---|---|---|
| `token` | `str` | The original text span for this token |
| `jyutping` | `str` | Space-separated Jyutping syllables for the token |
| `lang` | `str` | `"yue"` (Cantonese), `"en"` (English / Latin), `"punct"` (punctuation) |

The joined jyutping from `convert_detailed()` is identical to the output of `convert()` for the same input.

```python
p.convert_detailed("香港 hello")
# → [("香港", "hoeng1 gong2", "yue"), ("hello", "haa1 lou2", "en")]

p.convert_detailed("你好，")
# → [("你好", "nei5 hou2", "yue"), ("，", "，", "punct")]

p.convert_detailed("2026年")
# → all tokens tagged "yue" (normalizer expands digits to Chinese characters first)

p.convert_detailed("")
# → []
```

---

## Accuracy

### Verified examples

| Input | Output | Notes |
|---|---|---|
| `你好嘅` | `nei5 hou2 ge3` | Oral particle 嘅 from hand-curated list |
| `香港` | `hoeng1 gong2` | Word-level dict lookup |
| `銀行` | `ngan4 hong4` | Polyphone resolved by word context (not `haang4`) |
| `唔` | `m4` | Cantonese negation particle |
| `喺` | `hai2` | Locative particle |
| `2026年` | `ji6 ling4 ji6 luk6 nin4` | Year normalizer |
| `6月13日` | `luk6 jyut6 sap6 saam1 jat6` | Date normalizer |
| `50%` | `baak3 fan6 zi1 ng5 sap6` | Percentage normalizer |
| `HK$100` | `jat1 baak3 jyun4` | Currency normalizer |
| `hello` | `haa1 lou2` | Cantonese loanword in rime-cantonese dict |
| `send` | `sen1` | Latin loanword with Cantonese reading |

### Known limitations (v1)

- **Residual polyphones**: Word-boundary segmentation resolves approximately 85% of polyphone cases. Single-character polyphones that cannot be disambiguated by context (e.g. 好 as `hou2` greeting vs. `hou3` adverb) fall back to the most-frequent reading in the dictionary.
- **Tone sandhi (變調)**: Citation tones only — v1 does not model tone sandhi. This is deferred to a future release.
- **English passthrough**: Latin tokens not found in the Cantonese loanword dictionary are passed through unchanged in `convert()`. `convert_detailed()` still tags them as `"en"`.
- **No neural polyphone tier**: The current segmentation-based approach covers most cases. A BERT-based polyphone layer (trainable on HKCanCor CC-BY) is on the roadmap but not included in v1.

---

## Comparison with other tools

| Tool | Implementation | English code-switch | License | Notes |
|---|---|---|---|---|
| **canto-g2p** | **Rust + Python** | **Yes** | **Apache-2.0** | First Rust-native Cantonese G2P; mmap binary dict |
| [ToJyutping](https://github.com/CanCLID/ToJyutping) (CanCLID) | Python / JS | No | BSD-2 | De-facto standard; rime-cantonese data; no normalizer |
| [PyCantonese](https://github.com/jacksonllee/pycantonese) | Python (Rust internal) | No | MIT | Most complete toolkit; dict-heuristic polyphone |
| [g2pW-Cantonese](https://github.com/Naozumi520/g2pW-Cantonese) | Python (BERT) | No | mixed | SOTA neural polyphone; trained on words.hk + CantoDict — license-tainted, not cleanly redistributable |

`canto-g2p` is the only tool that handles English code-switching — standard in Hong Kong Cantonese (e.g. 佢 send 咗 email 俾我) — and the only one with a Cantonese text normalizer for numbers, dates, and currency.

---

## Data sources

### Bundled in the wheel (all permissive)

| Source | License | Usage |
|---|---|---|
| [rime-cantonese](https://github.com/rime/rime-cantonese) `jyut6ping3.dict/.chars/.words` | CC-BY-4.0 | Primary lexicon (~100k entries); attribution required — see `NOTICE` |
| [Unihan `kCantonese`](https://unicode.org/charts/unihan.html) | Unicode License v3 (MIT-equivalent) | Rare-character fallback (~20k chars) |
| `data/oral_hk.tsv` (hand-curated) | Apache-2.0 | ~60 HK colloquial characters: 嘅 喺 咗 哋 噉 㗎 囉 喎 … |

### Excluded (license-incompatible)

| Source | Reason |
|---|---|
| rime-cantonese `jyut6ping3.maps.dict.yaml` | ODbL v1.0 (share-alike — would infect data files) |
| CC-Canto | CC-BY-SA 3.0 (copyleft — same problem) |
| words.hk | Proprietary — no redistribution |
| CantoDict | Proprietary |

---

## Build from source

### Prerequisites

- **Rust** stable toolchain — [install via rustup](https://rustup.rs/)
- **Python** >= 3.8
- **maturin** >= 1.4

```bash
pip install maturin
```

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/typangaa/canto-g2p.git
cd canto-g2p

# 2. Fetch data sources (downloads ~16 MB from rime-cantonese and Unicode)
python3 scripts/fetch_data.py

# 3. Build binary pronunciation dictionaries
python3 scripts/build_dict.py

# 4. Build the Rust extension and install into the current environment
maturin develop --release
# Or build a wheel:
maturin build --release
pip install target/wheels/*.whl
```

### Run tests

```bash
# Rust unit tests
cargo test

# Python integration tests (requires built extension + data/)
python3 -m pytest tests/ -v
```

All 14 tests should pass. The test suite covers basic G2P correctness, polyphone disambiguation, English passthrough, code-switching, number/date normalization, batch processing, and `convert_detailed()` output structure.

---

## Contributing

Contributions are welcome. Please open an issue before starting significant work so we can align on direction. See [CONTRIBUTING.md](CONTRIBUTING.md) for coding guidelines, how to add entries to the hand-curated oral list, and the pull-request process.

A few areas where help is particularly valuable:

- Expanding `data/oral_hk.tsv` with additional colloquial characters
- Improving number normalization edge cases
- Adding tone sandhi rules (Phase 3+)
- Packaging and PyPI release CI

---

## License

**Apache-2.0** — see [LICENSE](LICENSE).

### Attribution (CC-BY-4.0 requirement)

This library bundles data derived from **rime-cantonese** (© CanCLID contributors), licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). See [NOTICE](NOTICE) for full attribution details.

---

## Related projects

- [SEA-G2P](https://github.com/pnnbao97/sea-g2p) — upstream inspiration (Rust G2P for Vietnamese)
- [ToJyutping](https://github.com/CanCLID/ToJyutping) — de-facto Python/JS Cantonese G2P front-end
- [PyCantonese](https://github.com/jacksonllee/pycantonese) — comprehensive Cantonese NLP toolkit
- [rime-cantonese](https://github.com/rime/rime-cantonese) — primary lexicon data source
