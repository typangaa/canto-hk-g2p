# canto-g2p

A fast Cantonese **text-to-phoneme (G2P)** converter — Rust core with Python (pyo3)
bindings. Modeled after [SEA-G2P](https://github.com/pnnbao97/sea-g2p) (Vietnamese),
but built for **Cantonese + English code-switching**, outputting **Jyutping with tone
numbers** (LSHK standard, all-ASCII).

> Status: **design / pre-scaffold**. This file records the agreed design so any
> session can resume. Greenfield repo (not yet git-init'd).

## Why this exists

Primary motivation is the **canto-tts** project (MOSS-TTS-Nano fine-tune). Current
problems a G2P layer solves:

| Problem | Symptom | G2P fixes it |
|---|---|---|
| `嘅`=2 tokens, `噉`=4 tokens | ~47k extra tokens, truncation risk | phonemize first → bypass rare chars |
| Cantonese chars not in MOSS vocab | model sees byte fragments | jyutping is all-ASCII |
| Training tone-hint rate only 15-20% | not every line has tone guidance | 100% coverage |
| Inference has no tone hint | unstable output tones | inject jyutping as pre-processing |

But the deliverable is a **standalone open-source library** — canto-tts is just one
consumer. It fills a real gap in Cantonese NLP (SEA-G2P did Vietnamese; nothing
equivalent exists for Cantonese with this design).

## Decided requirements (locked)

1. **Scope**: standalone open-source library (pip-installable, docs, CI).
2. **Output**: Jyutping + tone numbers, e.g. `nei5 hou2 ge3`. All-ASCII.
3. **Implementation**: Rust core + pyo3 / maturin Python bindings.
4. **Data — permissive licenses ONLY** (no copyleft/share-alike, no restricted sources):
   - `rime-cantonese` `jyut6ping3.dict/.chars/.words/.phrase` — **CC-BY-4.0** (attribution only). ✅
   - Unihan `kCantonese` field — **Unicode License** (permissive). ✅ char-level OOV fallback.
   - Hand-curated HK colloquial chars (~60: 嘅喺咗哋噉㗎囉喎…) — our own (MIT). ✅
   - **EXCLUDE** rime-cantonese `jyut6ping3.maps` (ODbL share-alike).
   - **EXCLUDE** CC-Canto (CC-BY-SA 3.0 copyleft — would infect the data file).
   - **EXCLUDE** words.hk (restricted redistribution).
5. **Tone sandhi (變調)**: **v1 skips it** — output citation tones. Future feature.

## Architecture (mirrors SEA-G2P)

```
text → [normalize] → [word segmentation] → [dict lookup → char fallback] → [EN passthrough] → jyutping
```

Key difference from SEA-G2P: Vietnamese is space-delimited; **Cantonese has no word
boundaries**, so a segmentation layer (DP / longest-match over the word dict) is
required. Word-level lookup also resolves **polyphones / 多音字** naturally
(行為→hang4 wai4 vs 行路→haang4 lou6); char fallback uses the most-frequent reading.

SEA-G2P performance tricks to reuse: **mmap binary dict** (`.bin`), **string pooling**
(unique strings stored once, referenced by 4-byte IDs), **binary search** O(log n),
**Rayon** batch parallelism.

## Planned repo structure

```
canto-g2p/
├── Cargo.toml
├── src/
│   ├── lib.rs            ← pyo3 bindings
│   ├── normalizer.rs     ← numbers/dates/punctuation (廿三→ji6 saam1, 六月十三日…)
│   ├── segment.rs        ← DP / longest-match segmentation over word dict
│   ├── g2p.rs            ← lookup → char fallback → EN passthrough
│   ├── pipeline.rs       ← orchestrate + Rayon batch
│   └── dict/{builder.rs, lookup.rs}   ← YAML/Unihan → .bin ; mmap + binary search
├── data/{word.bin, char.bin, oral_hk.bin}
├── python/canto_g2p/     ← Python package (maturin)
├── scripts/fetch_data.py ← download sources + build .bin (record source versions)
├── tests/
├── LICENSE + NOTICE      ← attribution: rime-cantonese (CC-BY-4.0), Unihan (Unicode)
└── README.md
```

## Target API

```python
from canto_g2p import Pipeline
p = Pipeline()
p.convert("你好嘅，I love Hong Kong")   # → "nei5 hou2 ge3 , I love hoeng1 gong2"
p.convert_batch([...])                   # Rayon-parallel
```

## Phased plan

| Phase | Content |
|---|---|
| 0. Scaffold | Cargo + maturin/pyo3 + pytest + CI |
| 1. Data ingest | fetch rime-cantonese + Unihan → build `.bin` (string pool + sorted) |
| 2. Core G2P | mmap lookup + DP segmentation + char fallback + EN passthrough (MVP) |
| 3. Normalizer | numbers/dates/percent/punctuation Cantonese reading rules |
| 4. Python API | pyo3 bindings + Pipeline + Rayon batch |
| 5. Polish | tests + benchmark + docs + LICENSE/NOTICE |
| 6. canto-tts integration | encoder: corpus → 100% jyutping hint; infer.py pre-processing |

## Ecosystem (researched June 2026)

**No Rust-native Cantonese G2P library exists** — canto-g2p is first-mover.

Existing tools (all Python/JS, none handle English code-switching):
| Tool | License | Notes |
|---|---|---|
| [PyCantonese](https://github.com/jacksonllee/pycantonese) | MIT | most complete toolkit; v4 uses Rust internally ("Rustling"); word-level G2P, dict-heuristic polyphone |
| [ToJyutping](https://github.com/CanCLID/ToJyutping) (CanCLID) | BSD-2 | de-facto G2P front-end for Cantonese TTS; word-level; jyutping + IPA; rime-cantonese data |
| [g2pW-Cantonese](https://github.com/Naozumi520/g2pW-Cantonese) | mixed | SOTA polyphone (BERT), but **trained on words.hk + CantoDict → license-tainted, NOT redistributable cleanly** ⚠️ |
| [jieba-rs](https://github.com/messense/jieba-rs) | MIT | best Rust segmentation base; needs Cantonese custom dict |
| [canto-filter / cantonesedetect](https://github.com/CanCLID/canto-filter) (CanCLID) | MIT/Apache | language ID — useful for token classification |

**English code-switching is handled by NO Cantonese tool** → canto-g2p's main differentiator
(HK Cantonese routinely mixes English: 佢 send 咗 email 俾我).

## Data stack — researched & verified (permissive only)

Bundled in the wheel (lookup dictionaries):
- **rime-cantonese** `jyut6ping3.dict/.chars/.words/.phrase` — **CC-BY-4.0**. ✅ primary lexicon (~100k entries)
- **Unihan `kCantonese`** — **Unicode License v3** (MIT-equiv). ✅ rare-char fallback (~20k chars)
- Hand-curated HK colloquial chars — our own (MIT/Apache). ✅

For FUTURE model training (not bundled, text only):
- **HKCanCor** — CC-BY — segmenter/polyphone training (~170k words, POS+jyutping tagged)
- **Common Voice zh-HK** — CC0 — transcriptions
- **WenetSpeech-Yue** — MIT code (verify dataset terms) — large-scale text

**NEVER bundle** (license-incompatible): rime-cantonese `.maps` (ODbL), CC-Canto (CC-BY-SA),
words.hk (proprietary), CantoDict (proprietary), Wiktionary (CC-BY-SA/GFDL).

## Finalized decisions (locked)

1. **English code-switching**: **passthrough in v1** (English tokens unchanged: `email`→`email`). CMU→IPA real code-switch deferred to a later feature.
2. **Polyphone (多音字)**: **dictionary / word-boundary only** in v1 (~85% via segmentation; char fallback uses most-frequent reading). Neural tier deferred (would be trained on HKCanCor CC-BY, NOT g2pW).
3. **Library license**: **Apache-2.0** (explicit patent grant + retaliation clause; single LICENSE file).
4. **Segmenter**: **own longest-match + word-frequency DP** over the word dict (zero-dep; jieba-rs deferred behind a future feature flag). Rationale: for G2P, segmentation only needs to catch polyphone-disambiguating multi-char words — per-char jyutping fallback covers the rest.

## Related

- Upstream inspiration: SEA-G2P (Rust, Vietnamese) — https://github.com/pnnbao97/sea-g2p
- Consumer project: canto-tts (MOSS-TTS-Nano fine-tune) — see ~/.claude memory `canto-tts-project`
- Full ecosystem report (agy/cloud): `~/.gemini/antigravity-cli/brain/863ba829-.../canto_g2p_ecosystem_report.md`
