# canto-hk-g2p

**Fast Cantonese text-to-phoneme (G2P) converter** — converts Cantonese (and English code-switched) text to Jyutping with tone numbers (LSHK standard, all-ASCII) or IPA. Rust core with Python bindings via PyO3/maturin.

[![CI](https://github.com/typangaa/canto-hk-g2p/actions/workflows/ci.yml/badge.svg)](https://github.com/typangaa/canto-hk-g2p/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/canto-hk-g2p)](https://pypi.org/project/canto-hk-g2p/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

```python
from canto_hk_g2p import Pipeline

p = Pipeline()
p.convert("你好嘅，I love Hong Kong")
# → "nei5 hou2 ge3 ， I love Hong Kong"
```

---

## Why this exists

Cantonese TTS systems struggle with two fundamental problems. First, colloquial Cantonese characters (嘅, 喺, 噉, 㗎, …) are rare or absent from standard Chinese vocabulary tables, causing tokenizers to split them into byte fragments that the model never learns to pronounce reliably. Second, Hong Kong Cantonese freely mixes English — a sentence like 佢 send 咗 email 俾我 is everyday speech — and no existing Cantonese G2P tool handles this cleanly.

`canto-hk-g2p` solves both: it converts the entire input, including colloquial particles, numbers, dates, and inline English, to all-ASCII Jyutping before the text ever reaches a TTS encoder. The result is stable, tone-accurate phoneme sequences with 100% coverage.

The library is a standalone open-source deliverable — Cantonese TTS pre-processing is the primary motivation, but the tool is useful anywhere Cantonese phonemization is needed.

---

## Features

- **All-ASCII Jyutping output** with LSHK tone numbers (`nei5 hou2 ge3`)
- **IPA output** — `convert_ipa()` with tone diacritics (`nei̯˩˧ hou̯˧˥ kɛː˧`) or tone numbers (`nei̯5 hou̯2 kɛː3`); English tokens converted via CMU Pronouncing Dictionary
- **English code-switching** — the only Cantonese G2P tool that handles mixed HK text; English tokens pass through unchanged in Jyutping mode (`佢 send 咗 email 俾我` → `keoi5 send zo2 email bei2 ngo5`), or converted to IPA in IPA mode
- **Punctuation normalisation** (`punc_norm=True` by default) — converts exotic punctuation to TTS-friendly equivalents before G2P: `「」《》` removed, `…` → `。`, `——` → `，`, `·` → space, `、` → `，`
- **Text normalization** — Arabic and full-width digits expanded to Cantonese spoken form:
  - Year: `2026年` → `ji6 ling4 ji6 luk6 nin4`
  - Date: `6月13日` → `luk6 jyut6 sap6 saam1 jat6`
  - Percentage: `50%` → `baak3 fan6 zi1 ng5 sap6`; decimal `50.5%` → `baak3 fan6 zi1 ng5 sap6 dim2 ng5`
  - Currency symbols: `HK$100` → `jat1 baak3 jyun4`; `¥500` → `ng5 baak3 jat6 jyun4`; `€200` → `ji6 baak3 au1 jyun4`
  - Currency codes: `USD100` → `jat1 baak3 mei5 jyun4`; `EUR 200` → `ji6 baak3 au1 jyun4`
  - Measurement units: `120km/h` → 一百二十公里每小時; `36.5°C` → 三十六點五攝氏度; `75kg` → 七十五公斤
  - Fractions: `1/2` → 二分之一; `3/4` → 四分之三
  - Scores: `3:1` → 三比一; `10:0` → 十比零
  - Ordinal/floor/episode: `第3名` → 第三名; `3樓` → 三樓; `第3集` → 第三集
  - Time: `下午3時15分` → Cantonese spoken time
  - Phone numbers: digit-by-digit expansion
- **Polyphone disambiguation** via longest-match word-level segmentation (~85% accuracy)
- **Rayon parallel batch processing** — scales to large corpora
- **Zero runtime Python dependencies** — pronunciation dictionaries bundled in the wheel
- **`convert_detailed()`** — structured `(token, jyutping, lang)` output with language tags (`yue` / `en` / `punct`)
- **Apache-2.0 license**, permissive data sources only — safe to redistribute

---

## Installation

```bash
# pip
pip install canto-hk-g2p

# uv (recommended — faster resolver)
uv pip install canto-hk-g2p

# uv project
uv add canto-hk-g2p
```

Pre-built wheels are available for Linux (x86\_64, aarch64), macOS (x86\_64, Apple Silicon), and Windows (x86\_64) for Python 3.8+. No Rust toolchain required for end users.

---

## Quick start

```python
from canto_hk_g2p import Pipeline

p = Pipeline()

# Basic Cantonese
p.convert("你好嘅")
# → "nei5 hou2 ge3"

# Full sentence with punctuation and English
p.convert("你好嘅，I love Hong Kong")
# → "nei5 hou2 ge3 ， I love Hong Kong"

# Punctuation normalisation (default on)
p.convert("《天氣之子》——一個故事")
# → "tin1 hei3 zi1 zi2 ， jat1 go3 gu3 si6"

# Number and date normalization
p.convert("2026年6月13日")
# → "ji6 ling4 ji6 luk6 nin4 luk6 jyut6 sap6 saam1 jat6"

p.convert("50%")
# → "baak3 fan6 zi1 ng5 sap6"

# English code-switching — Latin tokens pass through unchanged
p.convert("佢send咗email俾我")
# → "keoi5 send zo2 email bei2 ngo5"

# Batch conversion (Rayon parallel)
p.convert_batch(["香港", "銀行", "你好嘅"])
# → ["hoeng1 gong2", "ngan4 hong4", "nei5 hou2 ge3"]

# Structured output with language tags
p.convert_detailed("香港 hello")
# → [("香港", "hoeng1 gong2", "yue"), ("hello", "hello", "en")]
```

---

## IPA output

```python
from canto_hk_g2p import Pipeline, jyutping_to_ipa

p = Pipeline()

# Cantonese → IPA with tone diacritics (default)
p.convert_ipa("你好嘅")
# → "nei̯˩˧ hou̯˧˥ kɛː˧"

# IPA with tone numbers
p.convert_ipa("你好嘅", tone="number")
# → "nei̯5 hou̯2 kɛː3"

# English code-switching → English tokens converted via CMU Pronouncing Dictionary
p.convert_ipa("佢 send 咗 email 俾我")
# → "kʰœːy̯˩˧ sɛnd tsɔː˧˥ iːmeɪl pei̯˧˥ ŋɔː˩˧"

# Unknown English words (OOV) pass through unchanged
p.convert_ipa("佢去MTR站")
# → "kʰœːy̯˩˧ hœːy̯˧˥ MTR tsaam6˨"

# Standalone utility — convert existing Jyutping strings to IPA
jyutping_to_ipa("hoeng1 gong2")
# → "hœːŋ˥ kɔːŋ˧˥"

jyutping_to_ipa("nei5 hou2 ge3", tone="number")
# → "nei̯5 hou̯2 kɛː3"
```

IPA tone marks: ˥ high level (1), ˧˥ high rising (2), ˧ mid level (3),
˨˩ low falling (4), ˩˧ low rising (5), ˨ low level (6).

`jyutping_to_ipa` is also importable directly from `canto_hk_g2p` as shown above, or from `canto_hk_g2p.ipa`.

---

## API reference

### `Pipeline(*, punc_norm=True)`

Loads the binary pronunciation dictionaries from the bundled `data/` directory. The pipeline object is reusable and thread-safe for batch calls.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `punc_norm` | `bool` | `True` | Enable punctuation normalisation. Converts `「」《》` (removed), `…`→`。`, `——`→`，`, `·`→space, `、`→`，` before G2P lookup. Set to `False` to disable. |

```python
p = Pipeline()                   # punc_norm on (default)
p2 = Pipeline(punc_norm=False)   # raw punctuation passthrough
```

---

### `convert(text: str) -> str`

Converts a string of Cantonese (or mixed Cantonese/English) text to space-separated Jyutping syllables.

| Parameter | Type | Description |
|---|---|---|
| `text` | `str` | Input text (UTF-8). May contain Cantonese characters, English words, digits, punctuation. |

**Returns:** `str` — space-separated Jyutping syllables. Punctuation tokens are preserved as-is. Latin tokens (English words, acronyms) are passed through unchanged.

```python
p.convert("銀行")          # → "ngan4 hong4"
p.convert("2026年")        # → "ji6 ling4 ji6 luk6 nin4"
p.convert("I love you")   # → "I love you"
p.convert("send")          # → "send"
p.convert("")              # → ""
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

### `convert_ipa(text: str, tone: str = "diacritic") -> str`

Converts text to IPA. Cantonese tokens use the Jyutping→IPA mapping table; English tokens are converted via the bundled CMU Pronouncing Dictionary (OOV words pass through unchanged).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | — | Input text (Cantonese, English, or mixed). |
| `tone` | `str` | `"diacritic"` | `"diacritic"` — IPA suprasegmental tone marks (˥˧˥˧˨˩˩˧˨). `"number"` — IPA phonemes with Jyutping tone digit as suffix. |

**Returns:** `str` — space-separated IPA string.

```python
p.convert_ipa("香港")
# → "hœːŋ˥ kɔːŋ˧˥"

p.convert_ipa("香港", tone="number")
# → "hœːŋ1 kɔːŋ2"

p.convert_ipa("send")     # English → CMU dict
# → "sɛnd"

p.convert_ipa("MTR")      # OOV → passthrough
# → "MTR"
```

---

### `jyutping_to_ipa(jyutping: str, tone: str = "diacritic") -> str`

Standalone utility — converts an existing space-separated Jyutping string to IPA. Non-Jyutping tokens (English, punctuation) pass through unchanged. Importable from `canto_hk_g2p` or `canto_hk_g2p.ipa`.

```python
from canto_hk_g2p import jyutping_to_ipa

jyutping_to_ipa("nei5 hou2 ge3")
# → "nei̯˩˧ hou̯˧˥ kɛː˧"

jyutping_to_ipa("hoeng1 gong2", tone="number")
# → "hœːŋ1 kɔːŋ2"
```

---

### `convert_detailed(text: str) -> list[tuple[str, str, str]]`

Returns a structured token-level breakdown. Each element is a 3-tuple `(token, jyutping, lang)`.

| Field | Type | Values |
|---|---|---|
| `token` | `str` | The original text span for this token |
| `jyutping` | `str` | Space-separated Jyutping syllables for the token; equals `token` for Latin passthrough |
| `lang` | `str` | `"yue"` (Cantonese), `"en"` (English / Latin), `"punct"` (punctuation) |

The joined jyutping from `convert_detailed()` is identical to the output of `convert()` for the same input.

```python
p.convert_detailed("香港 hello")
# → [("香港", "hoeng1 gong2", "yue"), ("hello", "hello", "en")]

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
| `USD100` | `jat1 baak3 mei5 jyun4` | Currency code normalizer |
| `¥500` | `ng5 baak3 jat6 jyun4` | Currency symbol normalizer (¥ → 日圓) |
| `120km/h` | `jat1 baak3 ji6 sap6 gung1 lei5 mui5 siu2 si4` | Unit normalizer |
| `36.5°C` | `saam1 sap6 luk6 dim2 ng5 sip3 si6 dou6` | Decimal + unit normalizer |
| `hello` | `hello` | Latin passthrough — not in Cantonese phoneme space |
| `send` | `send` | Latin passthrough — English token in HK code-switching |
| `佢send咗email俾我` | `keoi5 send zo2 email bei2 ngo5` | Full code-switch sentence |

### Known limitations

- **Residual polyphones**: Word-boundary segmentation resolves approximately 85% of polyphone cases. Single-character polyphones that cannot be disambiguated by context (e.g. 好 as `hou2` greeting vs. `hou3` adverb) fall back to the most-frequent reading in the dictionary.
- **Fraction `十分之`**: Fractions with denominator 十 (e.g. `1/10`) output `fan1` instead of `fan6` because `十分之` is also a common adverb (十分之好 = "extremely good") — the adverb entry in rime-cantonese takes longest-match priority. Other denominators (1/2, 1/3, 3/4, 1/12 …) produce the correct `fan6` reading.
- **Tone sandhi (變調)**: Citation tones only — tone sandhi is deferred to a future release.
- **No neural polyphone tier**: The current segmentation-based approach covers most cases. A BERT-based polyphone layer (trainable on HKCanCor CC-BY) is on the roadmap but not included in v1.

---

## Comparison with other tools

| Tool | Implementation | English code-switch | License | Notes |
|---|---|---|---|---|
| Tool | Implementation | English code-switch | IPA output | License | Notes |
|---|---|---|---|---|---|
| **canto-hk-g2p** | **Rust + Python** | **Yes** | **Yes (CMU dict)** | **Apache-2.0** | First Rust-native Cantonese G2P; mmap binary dict; text normalizer |
| [ToJyutping](https://github.com/CanCLID/ToJyutping) (CanCLID) | Python / JS | No (letter-by-letter) | Yes | BSD-2 | De-facto standard; rime-cantonese data; no normalizer |
| [PyCantonese](https://github.com/jacksonllee/pycantonese) | Python (Rust internal) | No | No | MIT | Most complete toolkit; dict-heuristic polyphone |
| [g2pW-Cantonese](https://github.com/Naozumi520/g2pW-Cantonese) | Python (BERT) | No | No | mixed | SOTA neural polyphone; trained on words.hk + CantoDict — license-tainted, not cleanly redistributable |

`canto-hk-g2p` is the only tool that handles English code-switching cleanly — standard in Hong Kong Cantonese (e.g. 佢 send 咗 email 俾我) — and the only one with a Cantonese text normalizer for numbers, dates, and currency. It now also provides full IPA output with English tokens converted via the CMU Pronouncing Dictionary.

---

## Data sources

### Bundled in the wheel (all permissive)

| Source | License | Usage |
|---|---|---|
| [rime-cantonese](https://github.com/rime/rime-cantonese) `jyut6ping3.dict/.chars/.words` | CC-BY-4.0 | Primary lexicon (~100k entries); attribution required — see `NOTICE` |
| [Unihan `kCantonese`](https://unicode.org/charts/unihan.html) | Unicode License v3 (MIT-equivalent) | Rare-character fallback (~20k chars) |
| `data/oral_hk.tsv` (hand-curated) | Apache-2.0 | ~60 HK colloquial characters: 嘅 喺 咗 哋 噉 㗎 囉 喎 … |
| [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) | BSD-2-Clause | English → IPA via ARPAbet mapping (~134k entries); used by `convert_ipa()` |

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
git clone https://github.com/typangaa/canto-hk-g2p.git
cd canto-hk-g2p

# 2. Fetch data sources (downloads ~20 MB: rime-cantonese, Unicode, CMU dict)
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

All 266 tests should pass. The test suite covers basic G2P correctness, polyphone disambiguation, English passthrough, code-switching, punctuation normalisation, number/date/unit/currency/fraction/score normalization, batch processing, `convert_detailed()` output structure, and IPA conversion (all initials, finals, tones, syllabic consonants, CMU English lookup).

---

## Contributing

Contributions are welcome. Please open an issue before starting significant work so we can align on direction. See [CONTRIBUTING.md](CONTRIBUTING.md) for coding guidelines, how to add entries to the hand-curated oral list, and the pull-request process.

A few areas where help is particularly valuable:

- Expanding `data/oral_hk.tsv` with additional colloquial characters
- Unit abbreviation expansion (`km`, `°C`, `kg` → Cantonese spoken form)
- Improving number normalization edge cases
- Adding tone sandhi rules (future release)
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
