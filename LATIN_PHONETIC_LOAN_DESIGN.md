# Design: Latin-letter / English-word phonetic-loan resolution

> Status: **research + design complete, NOT scheduled for implementation.**
> Explicit decision (2026-07-19): this is documented purely for future
> reference. Do **not** implement against the current release based on this
> document alone — re-confirm scope with the user first, since risk
> tolerance or priorities may have changed by the time this is picked up.
> Companion to the existing `variant_words.tsv` 借音字 alias layer
> (CJK→CJK), but for a structurally different problem: Latin→CJK phonetic
> substitution.

## 1. The phenomenon

Hong Kong internet Cantonese (LIHKG, HKGolden, WhatsApp, Instagram/Threads)
routinely writes a Cantonese morpheme using a Latin letter or English word
that sounds like it, instead of the Chinese character — **not** genuine
English code-switching (the English word's *meaning* is irrelevant; only its
*sound* is borrowed):

| Latin | Cantonese | Jyutping | Example |
|---|---|---|---|
| `d` | 啲 | `di1` | 個d / 快d / 多d |
| `m` | 唔 | `m4` | m係 / m好 |
| `up` | 噏 | `ap1` | 亂up / 9up |
| `pea` | 皮 | `pei4` | 收pea |
| `duck` | 得 | `dak1` | duck唔duck |
| `law` | 攞 / 囉 | `lo2` / `lo1` | law嘢 / 咪係law |
| `on9` | 戇鳩 | `ngong6 gau1` | on9 / on99 |
| `hard glue` | 硬膠 | `ngaang6 gaau1` | — |
| `cheese sin` | 黐線 | `ci1 sin3` | — |
| `delay no more` | 丟你老母 | `diu2 nei5 lou5 mou2` | — |

Researched this turn via 4 parallel `weir chat agy-gemini` passes (single
Latin letters, full English words, academic terminology, prevalence). Key
findings:

- **Named linguistic phenomenon**: David C.S. Li (2000), *"Phonetic
  Borrowing: Key to the vitality of written Cantonese in Hong Kong"* —
  coins this **字母假借 / alphabetic phonetic loan** (an alphabetic-era
  extension of the classical Chinese 假借 jiǎjiè mechanism). Also studied
  under "letter words" (字母詞) and "Loose Cantonese Romanization (LCR)".
- **Prevalence**: estimated 3–10% of informal HK forum/chat sentences
  contain `d` for 啲 alone. Not a rare curiosity — a real gap.
- **Closed class**: unlike genuine code-switching (any English noun/verb,
  freely productive), this is a small, conventionalized inventory. New
  items appear occasionally (internet slang churns) but the mechanism
  itself does not generalize to arbitrary Latin spelling.
- **None of our bundled/reference corpora contain it**: HKCanCor and Common
  Voice zh-HK are transcriptions of speech into standard characters — this
  is purely a *written* CMC (computer-mediated-communication) phenomenon,
  so we have no existing corpus signal to lean on. The seed list must be
  hand-curated + verified the same way `variant_words.tsv` was.

## 2. Why this needs new architecture, not a `variant_words.tsv` row

Confirmed by reading `src/segment.rs` directly: text is split into runs by
Unicode block **before any dictionary lookup happens**:

```rust
fn run_kind(c: char) -> RunKind {
    match c as u32 {
        0x4E00..=0x9FFF => RunKind::Cjk,
        0x41..=0x5A | 0x61..=0x7A | 0x30..=0x39 => RunKind::Latin,
        _ => RunKind::Other,
    }
}
```

`flush_run()` (`src/segment.rs:76`) pushes a `Latin` run straight to
`tokens` unchanged — it never enters `segment_cjk()`, so it never touches
`word_dict`. Then `token_to_jyutping()` (`src/g2p.rs:29`) hits `is_cjk()` on
that same token and returns it verbatim (step 1, passthrough), before
`user_dict`/`word_dict`/`char_dict` are even consulted.

`variant_words.tsv` only ever populates `word_entries` (the CJK dict), so
pointing a Latin key at it is architecturally impossible without touching
these two files. This is a **new subsystem**, not a data-file addition.

## 3. The core risk: false positives against genuine English

The closed-class strings are not nonsense syllables — several are real
English words/abbreviations that legitimately appear in code-switched
Cantonese text or as loanwords/units:

- `d` → could be "Vitamin D" (`維他命D`), a grade, a disc size
- `on` → could be genuine English "on" in a code-switched clause
- `so`, `law`, `car`, `fan`, `die` → all real, common English words
- `k` → could be "K" as in kilobytes, or `卡拉OK`

Blind regex replacement of these strings anywhere near CJK text would
silently corrupt unrelated text. This is a **materially bigger risk class**
than the segmentation-collision risk documented for `variant_words.tsv`,
because the failure mode is *silent wrong output on ordinary sentences*,
not just a shadowed rare word.

### Proposed mitigation: adjacency, not proximity

The distinguishing structural signal (visible in the very examples
collected): phonetic-loan usage **fuses the Latin token directly onto a
CJK character with zero separator** (個**d**, 快**d**, 亂**up**, 收**pea**),
whereas genuine code-switching is separated by whitespace or punctuation
from the surrounding Cantonese (`你好嘅，I love Hong Kong` — comma-and-space
delimited). So the rule should require:

> Trigger the substitution **only** when the Latin run is immediately
> adjacent (no `Other`-run token in between — i.e. no space, no punctuation)
> to a CJK run on **at least one side**, AND the Latin run's lowercased text
> exactly matches an entry in a small, curated closed-class table.

This still does not fully solve `維他命D` (真係会撞——"命" directly touches
"D" with no separator). Two options to handle that residual risk, to
decide before implementing:

1. **Exclude single letters entirely from v1.** Multi-letter items (`up`,
   `pea`, `duck`, `law`, `on9`, `hard glue`, `cheese sin`, `delay no more`)
   have near-zero collision risk — nobody writes "Vitamin Up" or "命law"
   touching a CJK character by accident. Single letters (`d`, `m`, `k`,
   `c`, `g`, `o`, `a`) carry real collision risk against units, grades,
   and abbreviations and would need a hand-curated exclusion list
   (`維他命`, `卡拉OK`, model numbers, etc.) before they're safe to ship.
   **Recommended**: ship multi-letter-only in a first version; revisit
   single letters later with an explicit blocklist once the mechanism is
   proven.
2. Ship single letters too, but gated by a companion exclusion-list file
   (`latin_phonetic_loan_exclude.tsv`: known CJK contexts where the
   adjacency rule must NOT fire, e.g. `維他命` + `D`). More coverage, more
   maintenance surface, more ways to get it subtly wrong.

## 4. Proposed implementation shape (once scope is confirmed)

- New data file `data/latin_phonetic_loan.tsv`:
  `latin_string<TAB>canonical_cjk_word` (mirrors `variant_words.tsv`'s
  format and header-comment conventions). Lookup is case-insensitive.
- New pre-segmentation normalization pass (new function in
  `src/normalizer.rs`, run before `segment_owned()` in `pipeline.rs`):
  scans the raw string for `CJK-adjacent Latin run` spans, checks the run
  (lowercased) against the loaded table, and rewrites matching spans to
  their canonical CJK text in-place before segmentation ever runs.
  Downstream (segmentation, word_dict lookup, `variant_alias` resolution)
  needs zero changes — the rewritten text is indistinguishable from a user
  who typed the Chinese characters directly.
- `build_dict.py`: load `latin_phonetic_loan.tsv` into a new sidecar (or
  fold into an existing lookup structure the normalizer reads at runtime —
  needs a decision: compile-time-embedded small table vs. another `.bin`).
  Given the list will likely stay under ~30 entries, a `phf`-style
  compile-time static map embedded directly in `normalizer.rs` may be
  simpler than a new mmap dict — no build-time data dependency at all.
- New `source` tag for the Candidates API, e.g. `"latin_phonetic_loan"`,
  so `convert_candidates()` can report provenance same as `variant_alias`.
- Tests: adjacency-triggers-substitution cases, adjacency-required-not-
  triggered-on-standalone-English cases (`I love Hong Kong` unaffected),
  and the `維他命D`-style false-positive regression guard if single letters
  are in scope.
- Versioning: this is new user-visible conversion behavior for previously
  passthrough text — likely a **minor** bump (new opt-in-by-default
  behavior, not a breaking API/output-shape change), e.g. v2.2.0.

## 5. Decisions locked this session

- **Matching unit**: the *entire* contiguous Latin run must exactly equal
  (case-insensitive) a table entry — never a substring match. This alone
  rules out a lot of naive false positives (e.g. a run of `"onward"`
  cannot match `"on9"` or `"on"`; a run of `"hahaha"` cannot match `"ha"`).
  The residual risk is specifically when a user's *entire* Latin run
  happens to equal a real English word AND is fused with zero separator
  to a CJK character (`維他命D`, `畀me`).
- **Architecture**: pre-segmentation text-rewrite (§4, option A) — confirmed.
- **Lookup table representation**: compile-time static map in
  `normalizer.rs` (no new `.bin`, no `build_dict.py` step) — confirmed.
- **Multi-word phrases rejected entirely** (`hard glue`, `cheese sin`,
  `delay no more`): these are plain, plausible English phrases that could
  appear as genuine code-switching (a person could really write "hard
  glue" meaning hard glue) — unlike single-run tokens like `on9`, `duck`,
  `up` which have no ordinary English reading in context. Per-user
  judgement, out of scope entirely, not just deferred. This also removes
  the need for multi-Latin-token phrase-matching logic — v1 only ever
  needs to classify **one** Latin run at a time.
- **Particle digrams (SFP set) are conceptually in scope**, but — per
  explicit user instruction — **every single candidate must be reviewed
  and confirmed individually before being added**, the same discipline
  used for `variant_words.tsv`. Nothing in §5a below is approved yet; it
  is a review list.

## 5a. Candidate review — final verdicts (2026-07-19, item-by-item)

Every single-Latin-run candidate was reviewed one at a time with the user.
Two corrections surfaced during review (both verified against the bundled
`data/raw/rime-cantonese/jyut6ping3.chars.dict.yaml` before finalizing):
the `ha` particle's actual target character is **下** (`haa5`), not 吓
(`吓` is `haa1`/`haa2`, an unrelated interjection) — an initial mix-up on
my part; and `ga`'s target glyph (U+35CE, a rare CJK Extension-A character)
repeatedly rendered incorrectly in chat despite being confirmed correct
byte-for-byte against source data — noted below since it affects how that
row should be handled if this is ever revisited.

| Latin | Cantonese | Jyutping | Example | Verdict |
|---|---|---|---|---|
| `d` | 啲 | `di1` | 個d / 快d / 多d | ❌ Reject |
| `m` | 唔 | `m4` | m係 / m好 | ❌ Reject |
| `up` | 噏 | `ap1` | 亂up / 9up | ✅ **Approve — restricted scope only**: fixed collocations `亂up`→亂噏, `9up`→9噏, `鳩up`→鳩噏. NOT a general "any CJK + up" rule — the user explicitly rejected the general form because "up" is a real English word. |
| `duck` | 得 | `dak1` | duck唔duck | ❌ Reject |
| `pea` | 皮 | `pei4` | 收pea | ❌ Reject |
| `on9` | 戇鳩 | `ngong6 gau1` | on9 / on99 | ✅ Approve |
| `fly` | 飛 | `fei1` | 買fly | ❌ Reject |
| `law` | 攞/囉 | disputed | law嘢 / 咪係law | ❌ Reject — disputed canonical target, same rejection class as 黎/嚟 |
| `ge` | 嘅 | `ge3` | 我ge | ✅ Approve |
| `la` | 啦 | `laa1` | 走la | ❌ Reject |
| `lo` | 囉 | `lo1` | 係噉lo | ❌ Reject |
| `me` | 咩 | `me1` | 真係me? | ❌ Reject — "me" is too common a genuine English pronoun |
| `wo` | 喎 | `wo3`/`wo5` | 佢話唔嚟喎 | ✅ Approve |
| `bo` | 啵 | `bo1`/`bo3` | 唔好唔記得啵 | ❌ Reject |
| `ga` | (U+35CE, 口+柬-like Extension-A char) | `gaa3` | 係ga | ⏸ **Deferred, not approved** — confirmed correct against source data three times, but the glyph would not render correctly across multiple attempts in this chat session. Before this can ship, whoever picks this up must open `data/raw/rime-cantonese/jyut6ping3.chars.dict.yaml` directly (search for `gaa3`) and visually confirm the character with the user outside of a chat transcript, rather than trusting any glyph typed in conversation. |
| `ja` | 咋 | `zaa3` | 一次咋 | ✅ Approve |
| `je` | 啫 | `ze1` | 講下啫 | ✅ Approve |
| `ha` | 下 *(corrected from 吓)* | `haa5` | 睇下 | ❌ Reject |
| `ma` | 嗎/嘛 | `maa1`/`maa3` | 係嗎? | ❌ Reject |

**Final approved set (6 of 19, pending `ga`'s deferred status):**
`on9`→戇鳩, `ge`→嘅, `wo`→喎, `ja`→咋, `je`→啫, plus `up` restricted to the
three fixed collocations `亂up`/`9up`/`鳩up`.

Even for this approved set, note the `up` case establishes that **not every
approved Latin string can use the simple "any-adjacency" rule** — some need
fixed two-token collocation matching (CJK-prefix + Latin-run, checked as a
unit) rather than a standalone Latin-run table lookup. This is an
additional implementation-complexity finding for whoever picks this up:
the mechanism in §4 needs at minimum two entry *kinds* — free-standing
Latin-run entries (`ge`, `wo`, `ja`, `je`, `on9`) and fixed-collocation
entries (`亂up`, `9up`, `鳩up`) — not one uniform table.

## 6. Open questions — resolved

1. ~~Ship single letters in v1?~~ Reviewed individually; only `ge` approved
   among the single/short-letter candidates (`d`, `m` rejected).
2. ~~Compile-time static map vs `.bin`?~~ Compile-time static map — decided.
3. ~~Pre-segmentation rewrite vs new resolve branch?~~ Pre-segmentation
   rewrite — decided. Note the consequence: `convert_detailed()`'s token
   for a resolved position will show the *canonical CJK word*, not the
   user's original Latin spelling (e.g. input `"個d"` → token `"啲"`, not
   `"d"`) — flagging this now since it's a real, visible behavior change
   from how every other token type in this pipeline currently works. This
   was never explicitly re-confirmed after the `d` candidate itself was
   rejected — re-check if/when this is picked up again.
4. ~~Multi-word phrases (`hard glue` etc.)?~~ Rejected — plausible genuine
   English, out of scope entirely.

## 7. Explicit decision: NOT going into this release

The user's instruction (2026-07-19): record and document this research and
these decisions for future reference; **do not implement it now**. No code,
no data file, no `normalizer.rs` changes, no version bump were made as part
of this session — this document is the only artifact. Nothing in the
existing `variant_words.tsv` / `variant_alias` mechanism (v2.1.0, already
shipped this session) is affected by or depends on this document.

If/when this is picked up again, still outstanding:
- Resolve `ga`'s glyph-confirmation issue outside of chat (see §5a).
- Decide the two-entry-kind table shape (free-standing vs fixed-collocation
  — see §5a's `up` note) before writing any code.
- Re-confirm the `convert_detailed()` canonical-word-as-token behavior
  (§6.3) is still acceptable.
- Re-confirm risk tolerance hasn't changed — this session rejected 13 of
  19 candidates specifically because the reviewer judged genuine-English
  collision risk unacceptable even for some LOW-risk-labeled items (e.g.
  `duck`, `pea`, `fly` were all rejected despite low labeled risk) —
  whoever revisits this should not assume the LOW/MEDIUM/HIGH labels in
  §5a predict the actual verdict.
