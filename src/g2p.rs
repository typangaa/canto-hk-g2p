use crate::dict::Dict;
use crate::user_dict::UserDict;

/// Classify whether a token should be treated as CJK Cantonese or English/other.
fn is_cjk(s: &str) -> bool {
    s.chars().any(|c| {
        matches!(c as u32,
            0x4E00..=0x9FFF   // CJK Unified Ideographs
            | 0x3400..=0x4DBF // CJK Extension A
            | 0x20000..=0x2A6DF // CJK Extension B
            | 0xF900..=0xFAFF // CJK Compatibility Ideographs
        )
    })
}

/// Convert a single token to its Jyutping representation.
///
/// Lookup order:
///   1. Non-CJK → passthrough immediately (Latin, punctuation, digits never touch dict)
///   2. user_dict exact match  (runtime override — highest priority)
///   3. word_dict exact match  (catches multi-char words + polyphone resolution)
///   4. char_dict per-character fallback  (single-char OOV), user_dict checked per-char too
pub fn token_to_jyutping<'a>(
    token: &str,
    word_dict: &'a Dict,
    char_dict: &'a Dict,
    user_dict: &'a UserDict,
) -> String {
    // 1. Non-CJK → passthrough (English, punctuation, digits)
    if !is_cjk(token) {
        return token.to_owned();
    }

    // 2. user_dict exact match (highest priority override)
    if let Some(jp) = user_dict.get(token) {
        return jp.to_owned();
    }

    // 3. Exact word lookup (CJK tokens only)
    if let Some(jp) = word_dict.lookup(token) {
        return jp.to_owned();
    }

    // 4. CJK char-by-char fallback via char_dict (user_dict still wins per-char)
    let mut result = String::new();
    for ch in token.chars() {
        let s = ch.to_string();
        if let Some(jp) = user_dict
            .get(&s)
            .or_else(|| word_dict.lookup(&s))
            .or_else(|| char_dict.lookup(&s))
        {
            if !result.is_empty() {
                result.push(' ');
            }
            result.push_str(jp);
        } else {
            // Truly unknown char — keep as-is
            if !result.is_empty() {
                result.push(' ');
            }
            result.push(ch);
        }
    }
    result
}

/// Full resolution of a single token (Phase 7b-4, 2.0.0 consolidation of
/// issues #12 and #13): the rank-ordered candidate readings, a categorical
/// confidence tag, and the data-layer source that produced the result.
#[derive(Debug, PartialEq, Eq, Clone)]
pub struct Resolution {
    /// Rank-ordered known readings (most-likely first). Length 1 unless the
    /// token (or, for an OOV single char, the character) has 2+ known
    /// readings in the bundled Candidates API data.
    pub candidates: Vec<String>,
    /// `"certain"` (no ambiguity), `"ranked"` (2+ candidates ordered by
    /// ToJyutping's own context-aware ranking — a real preference signal),
    /// or `"tied"` (2+ candidates, but the order is rime-cantonese's raw
    /// arbitrary tie-break — no real signal; also the default when an
    /// ambiguous token has no entry in the confidence sidecar).
    pub confidence: String,
    /// Which data layer produced `candidates[0]`: `"rime"`, `"tojyutping"`
    /// (exact trie rank-0 hit), `"tojyutping_tiebreak"` (rime tie resolved
    /// via ToJyutping's context-aware segmentation, v1.7.1),
    /// `"oral_hk"` (hand-curated override), `"unihan"` (char-only fallback),
    /// `"user_dict"` (caller-supplied runtime override), `"passthrough"`
    /// (non-CJK — never touches a dict), `"char_fallback"` (OOV multi-char
    /// token resolved via the per-character loop — architecturally
    /// unreachable through real segmenter output, see known limitation),
    /// `"unresolved"` (truly unknown char, kept as-is), or `"unknown"` (the
    /// source sidecar has no entry / is missing for a dict hit — older or
    /// custom data dirs).
    pub source: String,
}

/// Resolve a single token to its full `Resolution` (candidates, confidence,
/// source) — the shared core behind `Pipeline::convert_detailed()` and
/// `Pipeline::convert_candidates()`.
///
/// Mirrors `token_to_jyutping`'s lookup order, but surfaces every known
/// alternate reading (rank-ordered, most-likely first) instead of committing
/// to a single one, plus where that reading and its ranking came from:
///   1. Non-CJK → passthrough, single candidate, `"passthrough"` source
///   2. user_dict exact match → single candidate (an override is a final
///      decision, not ambiguity to report), `"user_dict"` source
///   3. word_candidates exact match → its full rank-ordered candidate list,
///      confidence from `word_candidates_confidence`, source from `word_source`
///   4. word_dict exact match (no known alternates) → single candidate,
///      `"certain"`, source from `word_source`
///   5. Single-char token → char_candidates / char_dict exact match if
///      present, mirroring 3/4 with the char-level sidecars
///   6. Otherwise falls back to `token_to_jyutping`'s single resolved
///      reading — this includes multi-char OOV tokens resolved via the
///      per-character fallback loop, where ambiguity is not surfaced (each
///      char's own candidates are not combined; see CHANGELOG known
///      limitation) — tagged `"char_fallback"`, or `"unresolved"` if the
///      char was truly unknown and kept as-is.
///
/// No numeric probability is exposed here by design — neither ToJyutping's
/// trie nor rime-cantonese's tied readings carry real frequency data, so a
/// float score would be fabricated (see CHANGELOG).
#[allow(clippy::too_many_arguments)]
pub fn resolve_token<'a>(
    token: &str,
    word_dict: &'a Dict,
    char_dict: &'a Dict,
    user_dict: &'a UserDict,
    word_candidates: Option<&'a Dict>,
    char_candidates: Option<&'a Dict>,
    word_candidates_confidence: Option<&'a Dict>,
    char_candidates_confidence: Option<&'a Dict>,
    word_source: Option<&'a Dict>,
    char_source: Option<&'a Dict>,
) -> Resolution {
    if !is_cjk(token) {
        return Resolution {
            candidates: vec![token.to_owned()],
            confidence: "certain".to_owned(),
            source: "passthrough".to_owned(),
        };
    }

    if let Some(jp) = user_dict.get(token) {
        return Resolution {
            candidates: vec![jp.to_owned()],
            confidence: "certain".to_owned(),
            source: "user_dict".to_owned(),
        };
    }

    if let Some(cands) = word_candidates.and_then(|d| d.lookup(token)) {
        let confidence = word_candidates_confidence
            .and_then(|d| d.lookup(token))
            .unwrap_or("tied")
            .to_owned();
        let source = word_source
            .and_then(|d| d.lookup(token))
            .unwrap_or("unknown")
            .to_owned();
        return Resolution {
            candidates: cands.split('|').map(str::to_owned).collect(),
            confidence,
            source,
        };
    }

    if let Some(jp) = word_dict.lookup(token) {
        let source = word_source
            .and_then(|d| d.lookup(token))
            .unwrap_or("unknown")
            .to_owned();
        return Resolution {
            candidates: vec![jp.to_owned()],
            confidence: "certain".to_owned(),
            source,
        };
    }

    if token.chars().count() == 1 {
        if let Some(cands) = char_candidates.and_then(|d| d.lookup(token)) {
            let confidence = char_candidates_confidence
                .and_then(|d| d.lookup(token))
                .unwrap_or("tied")
                .to_owned();
            let source = char_source
                .and_then(|d| d.lookup(token))
                .unwrap_or("unknown")
                .to_owned();
            return Resolution {
                candidates: cands.split('|').map(str::to_owned).collect(),
                confidence,
                source,
            };
        }

        if let Some(jp) = char_dict.lookup(token) {
            let source = char_source
                .and_then(|d| d.lookup(token))
                .unwrap_or("unknown")
                .to_owned();
            return Resolution {
                candidates: vec![jp.to_owned()],
                confidence: "certain".to_owned(),
                source,
            };
        }
    }

    // Multi-char OOV fallback (architecturally unreachable via real
    // segmenter output — segment_owned() only ever emits a multi-char token
    // on an exact word_dict/user_dict hit) or a truly-unknown single char.
    let jp = token_to_jyutping(token, word_dict, char_dict, user_dict);
    let source = if jp == token {
        "unresolved"
    } else {
        "char_fallback"
    };
    Resolution {
        candidates: vec![jp],
        confidence: "certain".to_owned(),
        source: source.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::io::Write;

    fn make_dict(pairs: &[(&str, &str)]) -> Dict {
        let mut sorted = pairs.to_vec();
        sorted.sort_by_key(|(k, _)| k.as_bytes().to_vec());

        let mut pool: Vec<u8> = Vec::new();
        let mut offsets: Vec<(u32, u16, u32, u16)> = Vec::new();
        for (key, val) in &sorted {
            let ks = pool.len() as u32;
            let kl = key.len() as u16;
            pool.extend_from_slice(key.as_bytes());
            let vs = pool.len() as u32;
            let vl = val.len() as u16;
            pool.extend_from_slice(val.as_bytes());
            offsets.push((ks, kl, vs, vl));
        }

        let mut out: Vec<u8> = Vec::new();
        out.extend_from_slice(b"CJYP");
        out.extend_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&(sorted.len() as u32).to_le_bytes());
        out.extend_from_slice(&(pool.len() as u32).to_le_bytes());
        for (ks, kl, vs, vl) in &offsets {
            out.extend_from_slice(&ks.to_le_bytes());
            out.extend_from_slice(&kl.to_le_bytes());
            out.extend_from_slice(&vs.to_le_bytes());
            out.extend_from_slice(&vl.to_le_bytes());
        }
        out.extend_from_slice(&pool);

        use std::time::{SystemTime, UNIX_EPOCH};
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("canto_g2p_g2p_test_{nanos}"));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&out).unwrap();
        drop(f);
        Dict::load(&path).unwrap()
    }

    fn user(pairs: &[(&str, &str)]) -> UserDict {
        UserDict::new(
            pairs
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
        )
    }

    fn res(candidates: &[&str], confidence: &str, source: &str) -> Resolution {
        Resolution {
            candidates: candidates.iter().map(|s| s.to_string()).collect(),
            confidence: confidence.to_string(),
            source: source.to_string(),
        }
    }

    #[test]
    fn test_english_passthrough_ignores_user_dict() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[]);
        let ud = user(&[("hello", "wrong")]);
        // Non-CJK tokens never touch any dict, including user_dict.
        assert_eq!(token_to_jyutping("hello", &wd, &cd, &ud), "hello");
    }

    #[test]
    fn test_user_dict_overrides_word_dict() {
        let wd = make_dict(&[("行為", "haang4 wai4")]);
        let cd = make_dict(&[]);
        let ud = user(&[("行為", "hang4 wai4")]);
        assert_eq!(token_to_jyutping("行為", &wd, &cd, &ud), "hang4 wai4");
    }

    #[test]
    fn test_no_user_dict_falls_back_to_word_dict() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        assert_eq!(
            token_to_jyutping("香港", &wd, &cd, &UserDict::new(HashMap::new())),
            "hoeng1 gong2"
        );
    }

    #[test]
    fn test_user_dict_overrides_per_char_fallback() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[("行", "hong4")]);
        let ud = user(&[("行", "hang4")]);
        // Token itself isn't a word_dict/user_dict entry, so falls into the
        // per-char loop — user_dict still wins there over char_dict.
        assert_eq!(token_to_jyutping("行", &wd, &cd, &ud), "hang4");
    }

    #[test]
    fn test_unknown_char_stays_unchanged() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[]);
        assert_eq!(
            token_to_jyutping("龘", &wd, &cd, &UserDict::new(HashMap::new())),
            "龘"
        );
    }

    #[test]
    fn test_user_dict_empty_map_behaves_like_no_user_dict() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(token_to_jyutping("香港", &wd, &cd, &ud), "hoeng1 gong2");
    }

    // ── resolve_token ─────────────────────────────────────────────────────────

    #[test]
    fn test_resolve_english_passthrough() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            resolve_token("hello", &wd, &cd, &ud, None, None, None, None, None, None),
            res(&["hello"], "certain", "passthrough")
        );
    }

    #[test]
    fn test_resolve_user_dict_override() {
        let wd = make_dict(&[("正經", "zing3 ging1")]);
        let cd = make_dict(&[]);
        let ud = user(&[("正經", "zing1 ging1")]);
        let wcands = make_dict(&[("正經", "zing3 ging1|zing1 ging1")]);
        let wconf = make_dict(&[("正經", "ranked")]);
        let wsrc = make_dict(&[("正經", "tojyutping")]);
        assert_eq!(
            resolve_token(
                "正經",
                &wd,
                &cd,
                &ud,
                Some(&wcands),
                None,
                Some(&wconf),
                None,
                Some(&wsrc),
                None
            ),
            res(&["zing1 ging1"], "certain", "user_dict")
        );
    }

    #[test]
    fn test_resolve_word_level_ranked_with_source() {
        let wd = make_dict(&[("正經", "zing3 ging1")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wcands = make_dict(&[("正經", "zing3 ging1|zing1 ging1")]);
        let wconf = make_dict(&[("正經", "ranked")]);
        let wsrc = make_dict(&[("正經", "tojyutping")]);
        assert_eq!(
            resolve_token(
                "正經",
                &wd,
                &cd,
                &ud,
                Some(&wcands),
                None,
                Some(&wconf),
                None,
                Some(&wsrc),
                None
            ),
            res(&["zing3 ging1", "zing1 ging1"], "ranked", "tojyutping")
        );
    }

    #[test]
    fn test_resolve_word_level_tied_with_tiebreak_source() {
        let wd = make_dict(&[("處理", "cyu2 lei5")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wcands = make_dict(&[("處理", "cyu2 lei5|cyu5 lei5")]);
        let wconf = make_dict(&[("處理", "tied")]);
        let wsrc = make_dict(&[("處理", "tojyutping_tiebreak")]);
        assert_eq!(
            resolve_token(
                "處理",
                &wd,
                &cd,
                &ud,
                Some(&wcands),
                None,
                Some(&wconf),
                None,
                Some(&wsrc),
                None
            ),
            res(&["cyu2 lei5", "cyu5 lei5"], "tied", "tojyutping_tiebreak")
        );
    }

    #[test]
    fn test_resolve_no_ambiguity_reports_source_and_certain() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wsrc = make_dict(&[("香港", "rime")]);
        assert_eq!(
            resolve_token(
                "香港",
                &wd,
                &cd,
                &ud,
                None,
                None,
                None,
                None,
                Some(&wsrc),
                None
            ),
            res(&["hoeng1 gong2"], "certain", "rime")
        );
    }

    #[test]
    fn test_resolve_missing_confidence_and_source_sidecars_default() {
        // word_candidates has a row, but neither confidence nor source
        // sidecar exists at all (older/custom data dir) — must default to
        // "tied" / "unknown", not panic.
        let wd = make_dict(&[("正經", "zing3 ging1")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wcands = make_dict(&[("正經", "zing3 ging1|zing1 ging1")]);
        assert_eq!(
            resolve_token(
                "正經",
                &wd,
                &cd,
                &ud,
                Some(&wcands),
                None,
                None,
                None,
                None,
                None
            ),
            res(&["zing3 ging1", "zing1 ging1"], "tied", "unknown")
        );
    }

    #[test]
    fn test_resolve_single_char_ambiguity_with_source() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[("行", "hong4")]);
        let ud = UserDict::new(HashMap::new());
        let ccands = make_dict(&[("行", "hong4|hang4|haang4")]);
        let cconf = make_dict(&[("行", "ranked")]);
        let csrc = make_dict(&[("行", "tojyutping")]);
        assert_eq!(
            resolve_token(
                "行",
                &wd,
                &cd,
                &ud,
                None,
                Some(&ccands),
                None,
                Some(&cconf),
                None,
                Some(&csrc)
            ),
            res(&["hong4", "hang4", "haang4"], "ranked", "tojyutping")
        );
    }

    #[test]
    fn test_resolve_single_char_no_ambiguity_reports_char_source() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[("龍", "lung4")]);
        let ud = UserDict::new(HashMap::new());
        let csrc = make_dict(&[("龍", "unihan")]);
        assert_eq!(
            resolve_token(
                "龍",
                &wd,
                &cd,
                &ud,
                None,
                None,
                None,
                None,
                None,
                Some(&csrc)
            ),
            res(&["lung4"], "certain", "unihan")
        );
    }

    #[test]
    fn test_resolve_multi_char_oov_fallback_is_char_fallback() {
        // Neither char is an exact word_dict/word_candidates hit, so this
        // falls through to the per-char fallback loop — candidates are NOT
        // combined across chars, matching token_to_jyutping's single result.
        let wd = make_dict(&[]);
        let cd = make_dict(&[("老", "lou5"), ("世", "sai3")]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            resolve_token("老世", &wd, &cd, &ud, None, None, None, None, None, None),
            res(&["lou5 sai3"], "certain", "char_fallback")
        );
    }

    #[test]
    fn test_resolve_truly_unknown_char_is_unresolved() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            resolve_token("龘", &wd, &cd, &ud, None, None, None, None, None, None),
            res(&["龘"], "certain", "unresolved")
        );
    }

    #[test]
    fn test_resolve_missing_all_sidecars_behaves_like_none() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            resolve_token("香港", &wd, &cd, &ud, None, None, None, None, None, None),
            res(&["hoeng1 gong2"], "certain", "unknown")
        );
    }
}
