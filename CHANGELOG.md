# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] — 2026-07-19

### Added — 借音字 (phonetic-loan) alias layer

Investigation triggered by a user report that `訓覺` (a common miswriting of
`瞓覺`, "to sleep") resolved to `fan3 gok3` instead of `fan3 gaau3`. Root
cause: `訓` genuinely reads `fan3` on its own (教訓, 訓練) — nothing wrong
there — but when the *specific word* `訓覺` borrows `瞓`'s sound, char-level
fallback has no way to know that and returns `訓`'s own native reading
instead. This is a distinct linguistic category from 多音字 (a character with
several legitimate readings, resolved via word-level segmentation, ~85%
coverage) and from 異體字 (true orthographic variants, e.g. 裡/裏, which share
the same reading and therefore carry no risk at all).

A systematic sample of 31 words across all three categories (多音字/借音字/
異體字) confirmed the 借音字 pattern was structural, not a one-off: 4/6
sampled 借音字 words produced a wrong reading via char fallback, while every
多音字 and 異體字 sample the tool got right (several initial "failures" in
that sample turned out to be the reporter's own mistaken expected values,
corrected after verification — e.g. 重複 is genuinely `cung4 fuk1`, not
`fuk6`).

- **`data/variant_words.tsv`** (new, Apache-2.0, hand-curated): maps a
  borrowed-sound miswriting to its correctly-spelled canonical word
  (`variant_spelling<TAB>canonical_spelling`). `build_dict.py` resolves each
  alias at build time by copying the canonical word's already-resolved
  reading verbatim — the alias can never drift out of sync with upstream
  data, since it's not a separately hand-typed jyutping string.
  - Seed entries: `訓覺→瞓覺`, `岩岩→啱啱`, `果度→嗰度`, `緊係→梗係` (the last
    three independently corroborated by public sources documenting these as
    common convenience miswritings on HK forums, e.g. LIHKG).
  - `黎`/`嚟` (a very common substitution, e.g. `過黎` for `過嚟`) was
    deliberately **not** added: research showed `嚟` itself has two attested
    standard readings (`lai4` and `lei4`), so there is no single unambiguous
    canonical reading to alias to. Documented in `CONTRIBUTING.md` as the
    bar for adding a case — the canonical word's own reading must be
    unambiguous in real usage.
- New source tag: **`"variant_alias"`** — additive to the `source` field
  from #13, not a breaking change (no existing tuple shape changes; it's a
  new possible string value). Distinguishes "this reading was corrected from
  a known miswriting" from `"oral_hk"` ("this is a genuine hand-curated
  colloquial particle").
- Deliberately **not** built as a general character-level substitution rule
  (`訓`→`瞓` everywhere): that would corrupt `訓` in `教訓`/`訓練`, where it
  has its own genuine, unrelated reading. The alias table only ever matches
  at the exact word boundary the segmenter already uses.
- Considered scraping words.hk (粵典) for a comprehensive list — rejected:
  its license is restricted-redistribution (excluded per project policy).
  Seed list is hand-compiled from public linguistic knowledge instead, same
  practice as the existing `oral_hk.tsv`. A systematic sweep against
  HKCanCor (CC-BY, human-annotated jyutping corpus, already an approved
  future data source) was proposed as the path to comprehensive coverage
  but deferred — not yet implemented.
- Also surfaced, out of scope for this release: `有D` (Latin letter `D`
  standing in for `啲`) — a different substitution category (Latin letter
  for a Cantonese word, not a Chinese-character variant) that the current
  English-passthrough design doesn't address.

**Follow-up expansion search #1** (manual, single-model): cross-checked ~20
further candidate substitutions against public sources and the pipeline
directly. Only one more confirmed, unambiguous case survived: `緊係→梗係`
("of course"; currently misread as `gan2 hai6` instead of `gang2 hai6`).
Rejected candidates and why:
- `响度`/`响處` (借 響 for 喺): `响度` already has a legitimate, arguably more
  common meaning ("loudness", acoustics term, `hoeng2 dou6`) — aliasing it
  to `喺度` would corrupt that real word. Genuine polysemy, not a clean
  substitution.
- `既` for `嘅`: same problem as `黎`/`嚟` — `既` is the *original* borrowed
  character `嘅` was created from (adding the mouth radical); which form is
  "correct" is itself an open community debate, not a resolved fact.
- `加左`/`睇左`/`求奇`/`使乜`: already produce the correct reading today,
  either via an existing word-level dict entry or because the ambiguous
  character's rank-0 candidate already happens to be the right one — no
  fix needed.

**Follow-up expansion search #2** (multi-agent, via `weir chat agy-gemini` ×4
in parallel — general web research, academic/dictionary sources, HK forum
discussion threads, and a targeted list of colloquial particles). Combined
output claimed ~75 candidates across the 4 agents; most were unreliable on
inspection (one agent's own table mapped `既→嘅` and `既→㗎` in adjacent rows,
contradicting itself; several claimed pairs — `貢`/`噉`, `茅`/`冇`, `挽`/`玩`,
`巧`/`好` — are phonetically too distant to be plausible sound-borrows and
read as fabricated). Every surviving candidate was independently checked
against the pipeline for a real reading divergence, checked against
`word_entries` for **segmentation collisions** (a longer real word sharing
the same prefix), and cross-checked with `WebSearch` where corroboration was
thin. **13 new confirmed entries** survived this filter:
`係度→喺度`, `念住→諗住`, `林住→諗住`, `禁掣→撳掣`, `㩒掣→撳掣`, `令女→靚女`,
`亂嗡→亂噏`, `晒氣→嘥氣`, `甘樣→噉樣`, `甘多→咁多`, `吾該→唔該`, `吾知→唔知`,
`吾好→唔好`. (`制掣→撳掣` was swapped for `㩒掣→撳掣` after further review: `㩒`
turned out to already resolve correctly on its own via rime-cantonese — `㩒`
and `撳` are true 異體字 for the same `gam6` reading, not a divergent-reading
pair, so this row is a source-tag reclassification rather than a correctness
fix. `制掣`, by contrast, genuinely mis-resolves — `zai3 zai3` instead of
`gam6 zai3` — but was dropped in favor of `㩒掣` per this same review.)

Notable rejections from this pass:
- **`個度→嗰度`**: initially added, then caught by a segmentation-collision
  check and removed — `個度` (2 chars) shadows the real word `度數` inside
  `個度數` ("this reading/number"), turning it into `個度`+`數` instead of
  `個`+`度數`. This is a new failure mode distinct from the "disputed
  canonical reading" rejections seen so far, and is now documented as a
  required check in `CONTRIBUTING.md` and `data/variant_words.tsv`'s header.
- **`個個→嗰個`**: rejected — `個個` already has its own common, correct,
  unrelated meaning ("everyone", `go3 go3`); aliasing would corrupt it.
- **`親你→襯你`** (借 親 for 襯, e.g. "呢件衫好親你" for "...好襯你"):
  linguistically well-motivated (親 only grammatically follows a verb, e.g.
  嚇親/撞親; 襯 means "to match/suit") and a real divergence (`can1` vs
  `can3`), but rejected on an **architecture mismatch**: `襯你` doesn't
  independently exist as a word_entries key (it's two separately-resolved
  single characters, not a fixed lexicalized compound), so there is no
  canonical target for the alias mechanism to copy from without inventing
  a fake dictionary word. A single-character `親→襯` alias was also
  rejected — `親` has its own genuine `can1` reading in `親人`/`父親`/`親愛`
  that a blanket alias would corrupt.
- **`吾`→`唔` as a single-character alias** (rather than the three specific
  compounds actually added) was considered — all three research passes
  flagged this substitution heavily as a well-known "5P字" — but rejected
  in favor of the narrower, already-established policy of word-boundary-only
  aliases (see the `訓`/`訓覺` precedent in the `variant_alias` design
  above): a blanket single-char rule carries meaningfully higher blast
  radius per row than enumerating specific compounds, for one row saved.
- **`尼度→呢度`**: only one research pass flagged this, and a targeted
  follow-up `WebSearch` found no independent corroboration — left out for
  insufficient evidence, same bar applied to `黎`/`嚟` and `响度`.

This reinforces the CHANGELOG's earlier point: comprehensive coverage needs
the proposed HKCanCor corpus-driven sweep, not further one-by-one guessing —
and multi-agent research fan-out finds more raw candidates faster, but does
not reduce the need for the same per-candidate verification rigor (pipeline
divergence check + collision check + corroboration bar).

### Internal

- `word_source.bin` entry count: 141,818 → 141,835 (+17 `variant_alias`
  entries total; no new `.bin` file, no `pyproject.toml` packaging change
  needed).
- Rust: 159 tests (unchanged, no new Rust logic — resolution is build-time
  Python). Python: 318 tests (+17 over v2.0.0's 301: 3 from the first
  expansion pass, 14 from the multi-agent expansion — 13 parametrized cases
  + 1 segmentation-collision regression guard for `個度數`).

## [2.0.0] — 2026-07-19

### Breaking changes — Migration guide

`convert_detailed()`, `convert_candidates()`, and `convert_candidates_batch()`
each gained two new trailing tuple fields — `confidence` and `source` (see
below). Any code that unpacks their tuples by exact arity needs updating:

```python
# Before (v1.x)
for token, jyutping, lang in p.convert_detailed(text):
    ...
for token, candidates, lang in p.convert_candidates(text):
    ...

# After (v2.0.0)
for token, jyutping, lang, confidence, source in p.convert_detailed(text):
    ...
for token, candidates, lang, confidence, source in p.convert_candidates(text):
    ...

# Or, if you don't need the new fields, unpack with a starred catch-all:
for token, jyutping, lang, *_ in p.convert_detailed(text):
    ...
```

`convert()` and `convert_batch()` (plain-string output) are **unchanged**.
`Pipeline.convert_candidates_scored()` / `convert_candidates_scored_batch()`
— added and removed within the same unreleased development cycle (never
published to PyPI) — no longer exist; their confidence tag is now always
present directly on `convert_candidates()`.

### Added

**`confidence` field** (closes
[#12](https://github.com/typangaa/canto-hk-g2p/issues/12)): lets a caller
distinguish a genuine near-tie polyphone from a strong lean when
thresholding a human-QA review queue, since candidate-list length alone
can only signal "2+ known readings," treating every ambiguity the same
regardless of how confident the underlying data actually is. One of:

- `"certain"` — a single known reading; no ambiguity to report.
- `"ranked"` — 2+ candidates, ordered by ToJyutping's own context-aware
  ranking — a real preference signal.
- `"tied"` — 2+ candidates, but the order is rime-cantonese's raw arbitrary
  tie-break — no real preference signal. Also the default when an
  ambiguous token has no entry in the bundled confidence data.

**No numeric probability is exposed, by design.** The obvious API shape
would be a float score per candidate (e.g. `0.82`/`0.18`). Before
implementing, we researched how comparable tools represent this:

- **g2pW** (SOTA neural Mandarin polyphone disambiguator) computes softmax
  probabilities internally, but its own public reference API
  (`GitYCC/g2pW`) exposes only a single committed phoneme per character —
  no ranked list, no probability.
- **pypinyin** (`heteronym=True`) and **ToJyutping** — the same class of
  rule/dictionary tool this library is built on — return a rank-ordered
  list with no numeric score at all.
- **WenetSpeech-Yue**, a large Cantonese speech corpus with a real
  `jyutping_confidence` field, derives it from ROVER voting agreement
  across 3 independent ASR systems transcribing real audio — an empirical
  signal we have no equivalent of (no audio, no ASR ensemble; our ordering
  comes from either ToJyutping's static ranking or rime's arbitrary
  tie-break).

No comparable text-only, rule/dictionary-based G2P tool exposes a numeric
confidence, and the one real-world example that does derives it from a
fundamentally different (audio-grounded) process. A fabricated float would
overclaim precision the underlying data doesn't have — the categorical tag
is the honest representation.

**`source` field** (closes
[#13](https://github.com/typangaa/canto-hk-g2p/issues/13)): names which
data layer produced the rank-0 (committed) reading — useful for building a
project-specific `user_dict` for domain proper nouns by distinguishing
"this reading came from the generic Unihan char fallback" (likely wrong for
a multi-character proper noun) from a real dictionary hit, or for debugging
whether a wrong reading traces back to a hand-curated override vs. a gap in
the bundled dictionaries. One of `"rime"`, `"tojyutping"` (exact trie hit),
`"tojyutping_tiebreak"` (rime tie resolved via ToJyutping's context
segmentation, v1.7.1), `"oral_hk"` (hand-curated override), `"unihan"`
(char-only fallback), `"user_dict"` (caller override), `"passthrough"`
(non-CJK), `"char_fallback"` (OOV multi-char token — architecturally
unreachable via real segmenter output), `"unresolved"` (truly unknown
char), or `"unknown"` (source sidecar missing/no entry).

```python
p.convert_candidates("正經")
# → [("正經", ["zing3 ging1", "zing1 ging1"], "yue", "tied", "tojyutping_tiebreak")]

p.convert_candidates("行")
# → [("行", ["haang4", "hang4", ...], "yue", "ranked", "tojyutping")]

p.convert_candidates("香港")
# → [("香港", ["hoeng1 gong2"], "yue", "certain", "rime")]

p.convert_detailed("香港 hello")
# → [("香港", "hoeng1 gong2", "yue", "certain", "rime"),
#     ("hello", "hello", "en", "certain", "passthrough")]
```

**`Pipeline.convert_detailed_batch(texts)`** — new Rayon-parallel batch
sibling of `convert_detailed()`, completing batch-parity across every
structured method (`convert_detailed_batch()` / `convert_candidates_batch()`).

### Changed (data layer)

- `scripts/build_dict.py`'s `build_candidates()` now also returns a
  confidence dict (`"ranked"` for entries sourced from ToJyutping's own
  candidate ranking, `"tied"` for rime-cantonese's raw tie-break fallback),
  written to two new sparse sidecars — `word_candidates_confidence.bin` /
  `char_candidates_confidence.bin` — with 1:1 key coverage against
  `word_candidates.bin` / `char_candidates.bin`.
- New **full-coverage** sidecars `word_source.bin` (141,818 entries) /
  `char_source.bin` (32,376 entries) — every `word.bin`/`char.bin` key
  tagged with its winning upstream layer, mirroring `word_entries`'/
  `char_entries`' own merge-priority chain exactly (verified 1:1 coverage
  via a build-time assertion). Real corpus breakdown: word source is
  93,012 rime / 47,457 tojyutping / 1,290 tojyutping_tiebreak / 59 oral_hk;
  char source is 30,149 tojyutping / 2,154 unihan / 57 oral_hk / 16 rime.
  This is a genuine data-size increase (total bundled data: 6.2 MiB →
  10.4 MiB) since, unlike the sparse confidence/candidates sidecars, source
  provenance is tracked for every dictionary entry, not just ambiguous ones.
- `pyproject.toml`'s `[tool.maturin] include` list updated with all four new
  sidecars (gitignored generated files that must be explicitly whitelisted
  for the wheel — a gap in v1.11.0's local-only development caught before
  release).

### Internal

New Rust `g2p::resolve_token()` (returns a `Resolution { candidates,
confidence, source }` struct) replaces the separate
`token_to_jyutping_candidates()` / `token_to_jyutping_candidates_scored()`
functions, unifying the shared lookup-order logic behind both
`Pipeline::convert_detailed()` and `Pipeline::convert_candidates()`.
159 Rust unit tests + 301 Python integration tests, all passing.

[2.0.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.9.0...v2.0.0

## [1.10.0] — 2026-07-19

### Added

**`Pipeline.convert_candidates_batch(texts)`** — Rayon-parallel batch sibling of
`convert_candidates()` (v1.9.0), closing the throughput gap with the rest of
the batch-capable API (`convert_batch()`, and `convert_detailed()` via a plain
loop). Same per-text output shape as `convert_candidates()`, one
`list[(token, candidate_readings, lang)]` per input text:

```python
p.convert_candidates_batch(["正經", "香港銀行"])
# → [
#      [("正經", ["zing3 ging1", "zing1 ging1"], "yue")],
#      [("香港", ["hoeng1 gong2"], "yue"), ("銀行", ["ngan4 hong4"], "yue")],
#    ]
```

Motivated by [#11](https://github.com/typangaa/canto-hk-g2p/issues/11):
`canto-hk-speech-pipeline` uses `convert_candidates()` to flag ambiguous
polyphone segments for priority human QA review over a multi-hundred-
thousand-row corpus — a Python-level loop over `convert_candidates()`
forfeited the parallelism `convert_batch()` already provides for the plain
conversion path.

New Rust method `Pipeline::convert_candidates_batch()` (`src/pipeline.rs`,
`texts.par_iter().map(...).collect()`, identical pattern to `convert_batch()`)
+ pyo3 binding (`src/lib.rs`). 2 new Rust unit tests + 4 new Python tests
(`tests/test_candidates.py`).

[1.10.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.9.0...v1.10.0

## [1.9.0] — 2026-07-18

### Added

**Candidates API — `Pipeline.convert_candidates(text)`** (Phase 7b-2)
- New method: `p.convert_candidates(text)` → `list[(token, candidate_readings, lang)]`,
  the text-level sibling of `convert_detailed()`. `candidate_readings` is a
  rank-ordered list (most-likely first); it has more than one entry only
  where the bundled data has 2+ known readings for that exact token (or, for
  an out-of-vocabulary single character, that character) — e.g.
  `p.convert_candidates("正經")` → `[("正經", ["zing3 ging1", "zing1 ging1"], "yue")]`
- Everything else — unambiguous words, English tokens, punctuation, and
  out-of-vocabulary multi-char tokens resolved via the per-character fallback
  loop — reports a single-item list, identical to what `convert_detailed()`
  already produces for that token (documented known limitation: ambiguity is
  not surfaced across a multi-char OOV fallback token's individual
  characters — this is architecturally unreachable in practice anyway, since
  the segmenter only ever emits a multi-char token when it's an exact
  `word_dict`/`user_dict` hit)
- A `user_dict` override (v1.8.0) always collapses to a single candidate — an
  override is a final decision, not ambiguity to report
- **No new binary format**: reuses the existing CJYP v1 `Dict` (mmap +
  binary search) format as-is — a candidate cell's value is simply
  `"reading1|reading2|..."`. Two new sparse sidecar files are bundled in the
  wheel, `word_candidates.bin` (11,030 entries, 326 KiB) and
  `char_candidates.bin` (9,661 entries, 261 KiB) — only keys with 2+ distinct
  known readings get a row (most of ~141k word / ~32k char entries have
  exactly one reading and need no row)
- `scripts/build_dict.py`: `load_tojyutping()` now keeps ToJyutping's full
  rank-ordered candidate list per trie node (previously only rank-0 survived
  past the build step); `load_rime_cantonese()` now also returns the actual
  competing readings for tied words (previously only *which* words were tied
  was tracked, the losing reading's text was discarded); new
  `build_candidates()` merges the two sources — ToJyutping's own ranking wins
  outright when present (more trustworthy — it reflects that package's
  context modelling), otherwise falls back to rime's tied readings with the
  already-resolved winner moved to rank 0. `oral_hk.tsv` overrides are
  excluded from candidates entirely (a hand-curated decision isn't ambiguity)
- Sidecars are loaded as `Option<Dict>` and are optional at runtime — a data
  directory without them (e.g. an older cached build) still loads fine;
  `convert_candidates()` simply reports no known ambiguity anywhere
- New Rust function `g2p::token_to_jyutping_candidates()` (mirrors
  `token_to_jyutping()`'s lookup order) + `Pipeline::convert_candidates()`
  (mirrors `convert_detailed()`)
- 8 new Rust unit tests (`g2p.rs`) + 5 new Rust unit tests (`pipeline.rs`,
  including a missing-sidecar graceful-fallback case) + 14 new Python tests
  (`tests/test_candidates.py`)

This completes the deferred Candidates API work split out in v1.8.0
(Phase 7b): 7b-1 was the runtime `user_dict` override, 7b-2 is this
text-level candidates surface.

[1.9.0]: https://github.com/typangaa/canto-hk-g2p/compare/v1.8.0...v1.9.0

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
