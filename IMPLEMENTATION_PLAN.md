# canto-g2p — Implementation Plan

> Rust core + PyO3 Cantonese G2P → Jyutping (tone numbers). Permissive-license OSS.
> Modeled on [SEA-G2P](https://github.com/pnnbao97/sea-g2p). See `CLAUDE.md` for locked
> requirements and the ecosystem/license research.

## 0. Design summary

```
Input (Cantonese + English mixed)
   │
   ▼
[1. Normalizer]      numbers / dates / currency / punctuation → spoken form
   │
   ▼
[2. Token classifier]   per-token: Cantonese | English | Numeric | Symbol  (Unicode-block)
   │
   ├── Cantonese ─► [3a. Segment]   longest-match / DP over word dict
   │                [3b. Lookup]    mmap binary dict (rime-cantonese CC-BY)
   │                [3c. Fallback]  char dict (Unihan) → most-frequent reading
   │
   └── English ───► [3d. EN path]   passthrough (v1; CMU→IPA deferred)
   │
   ▼
Output: "nei5 hou2 ge3 , I love hoeng1 gong2"   (+ optional structured: [(tok, code, lang)])
```

Performance pattern reused from SEA-G2P: **mmap `.bin` dict**, **string pool** (4-byte IDs),
**binary search** O(log n), **Rayon** batch parallelism. Target: dict-only path, no neural
deps in core → `pip install canto-g2p` just works, zero runtime deps.

Word-level lookup resolves ~85% of polyphones (多音字) for free via segmentation
(行為→hang4 wai4 vs 行路→haang4 lou6). v1 ships **citation tones only** — no pinjam (變音),
no tone sandhi (Cantonese has no productive sandhi; pinjam is lexical, deferred).

## 1. Phases & deliverables

### Phase 0 — Scaffold
- `cargo init --lib`; `Cargo.toml` with `pyo3`, `memmap2`, `rayon`, `serde`.
- `maturin` build backend; `pyproject.toml`; `pip install -e .` works.
- `tests/` (pytest) + Rust `#[test]`; GitHub Actions CI (build + test on linux).
- `LICENSE` (**Apache-2.0**) + `NOTICE` (attribution: rime-cantonese CC-BY-4.0, Unihan Unicode License).
- **Exit:** empty `Pipeline().convert("")` round-trips through Rust↔Python.

### Phase 1 — Data ingest & binary dict
- `scripts/fetch_data.py`: download rime-cantonese (pin a commit SHA) + Unihan `Unihan_Readings.txt`; record source versions in `data/SOURCES.md`.
- Parse `jyut6ping3.dict/.chars/.words/.phrase` (YAML) → word→jyutping pairs. **Skip `.maps`.**
- Parse Unihan `kCantonese` → char→jyutping (most-frequent first).
- `src/dict/builder.rs`: emit `.bin` (sorted entries, string pool, 4-byte IDs).
- `src/dict/lookup.rs`: mmap + binary search.
- Curate `data/oral_hk.tsv` (~60 HK colloquial chars) → folded into char.bin.
- **Exit:** `lookup("你好")` → `nei5 hou2`; `lookup("嘅")` → `ge3`.

### Phase 2 — Core G2P (MVP)
- `src/segment.rs`: own longest-match (forward max-match) + word-frequency DP over word dict; fallback to single chars. (No jieba-rs dep.)
- `src/g2p.rs`: segment → word lookup → char fallback → English passthrough.
- `src/g2p.rs` token classifier (Unicode block: CJK vs Latin vs digit vs punct).
- **Exit:** `convert("你好嘅，I love Hong Kong")` → `nei5 hou2 ge3 , I love hoeng1 gong2`.

### Phase 3 — Normalizer
- `src/normalizer.rs`: Cantonese number reading (二 ji6 vs 兩 loeng5; 零 ling4 placeholder),
  years digit-by-digit (2026→ji6 ling4 ji6 luk6), dates (6月13日→luk6 jyut6 sap6 saam1 hou6),
  phone numbers, percent/currency, punctuation normalization.
- Runs *before* segmentation.
- **Exit:** golden-file tests for each number/date class pass.

### Phase 4 — Python API & batch
- `src/lib.rs` PyO3: `Pipeline`, `convert(str)->str`, `convert_batch(list)->list` (Rayon), optional `convert_detailed(str)->List[(tok,code,lang)]`.
- Type stubs (`.pyi`); docstrings.
- **Exit:** published API matches `CLAUDE.md` target; batch is parallel.

### Phase 5 — Polish & release-ready
- Test corpus: hand-labeled sentences covering particles, polyphones, code-switch, numbers.
- Benchmark (criterion + py timing) vs ToJyutping/PyCantonese for accuracy & speed.
- README (usage, license/attribution, accuracy table), `CONTRIBUTING.md`.
- Build wheels (manylinux via maturin); optional publish to PyPI/crates.io.
- **Exit:** green CI, wheel installs clean in fresh venv.

### Phase 6 — canto-tts integration
- Encoder script: corpus text → 100% jyutping hint (replaces current 15-20% rate).
- Hook into `infer.py` as pre-processing (inject jyutping before MOSS).
- **Exit:** canto-tts v1.5 training data has 100% tone-hint coverage.

## 2. Future / optional (post-v1, behind feature flags)
- **Neural polyphone tier** — train a small classifier on **HKCanCor (CC-BY)** only (NOT g2pW — license-tainted); ship as optional `canto-g2p[neural]` extra (ONNX/candle).
- **English G2P** — embed CMU dict (BSD) for English→ARPAbet/IPA if decision #1 chooses real code-switch later.
- **Pinjam (變音) lexicon** — lexical exception list for changed-tone words.
- WASM build; mobile (uniffi) bindings.

## 3. Risks
- **Segmentation quality** on slang — mitigate with rime-cantonese word list + HKCanCor frequencies.
- **Polyphone tail** beyond word-boundary — accept ~85% in v1, document; neural tier later.
- **License hygiene** — `data/SOURCES.md` records every source + license; CI lint asserts no forbidden source strings.

## 4. Finalized decisions (locked)
1. English: **passthrough v1** (CMU→IPA deferred).
2. Polyphone: **dict / word-boundary only** v1 (neural tier deferred).
3. License: **Apache-2.0**.
4. Segmenter: **own longest-match + word-frequency DP** (zero-dep).
