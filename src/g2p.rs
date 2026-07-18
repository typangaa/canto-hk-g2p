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

/// Convert a single token to its Jyutping candidate readings (Phase 7b-2).
///
/// Mirrors `token_to_jyutping`'s lookup order, but surfaces every known
/// alternate reading (rank-ordered, most-likely first) instead of committing
/// to a single one:
///   1. Non-CJK → passthrough, single candidate
///   2. user_dict exact match → single candidate (an override is a final
///      decision, not ambiguity to report)
///   3. word_candidates exact match → its full rank-ordered candidate list
///   4. word_dict exact match (no known alternates) → single candidate
///   5. Single-char token → char_candidates exact match if present
///   6. Otherwise falls back to `token_to_jyutping`'s single resolved
///      reading — this includes multi-char OOV tokens resolved via the
///      per-character fallback loop, where ambiguity is not surfaced (each
///      char's own candidates are not combined; see CHANGELOG known
///      limitation)
pub fn token_to_jyutping_candidates<'a>(
    token: &str,
    word_dict: &'a Dict,
    char_dict: &'a Dict,
    user_dict: &'a UserDict,
    word_candidates: Option<&'a Dict>,
    char_candidates: Option<&'a Dict>,
) -> Vec<String> {
    if !is_cjk(token) {
        return vec![token.to_owned()];
    }

    if let Some(jp) = user_dict.get(token) {
        return vec![jp.to_owned()];
    }

    if let Some(cands) = word_candidates.and_then(|d| d.lookup(token)) {
        return cands.split('|').map(str::to_owned).collect();
    }

    if let Some(jp) = word_dict.lookup(token) {
        return vec![jp.to_owned()];
    }

    if token.chars().count() == 1 {
        if let Some(cands) = char_candidates.and_then(|d| d.lookup(token)) {
            return cands.split('|').map(str::to_owned).collect();
        }
    }

    vec![token_to_jyutping(token, word_dict, char_dict, user_dict)]
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

    // ── token_to_jyutping_candidates ────────────────────────────────────────

    #[test]
    fn test_candidates_english_passthrough() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            token_to_jyutping_candidates("hello", &wd, &cd, &ud, None, None),
            vec!["hello".to_string()]
        );
    }

    #[test]
    fn test_candidates_word_level_ambiguity() {
        let wd = make_dict(&[("正經", "zing3 ging1")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wcands = make_dict(&[("正經", "zing3 ging1|zing1 ging1")]);
        assert_eq!(
            token_to_jyutping_candidates("正經", &wd, &cd, &ud, Some(&wcands), None),
            vec!["zing3 ging1".to_string(), "zing1 ging1".to_string()]
        );
    }

    #[test]
    fn test_candidates_no_ambiguity_falls_back_to_single_word_reading() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        let wcands = make_dict(&[]);
        assert_eq!(
            token_to_jyutping_candidates("香港", &wd, &cd, &ud, Some(&wcands), None),
            vec!["hoeng1 gong2".to_string()]
        );
    }

    #[test]
    fn test_candidates_single_char_ambiguity() {
        let wd = make_dict(&[]);
        let cd = make_dict(&[("行", "hong4")]);
        let ud = UserDict::new(HashMap::new());
        let ccands = make_dict(&[("行", "hong4|hang4|haang4")]);
        assert_eq!(
            token_to_jyutping_candidates("行", &wd, &cd, &ud, None, Some(&ccands)),
            vec![
                "hong4".to_string(),
                "hang4".to_string(),
                "haang4".to_string()
            ]
        );
    }

    #[test]
    fn test_candidates_user_dict_overrides_and_collapses_ambiguity() {
        let wd = make_dict(&[("正經", "zing3 ging1")]);
        let cd = make_dict(&[]);
        let ud = user(&[("正經", "zing1 ging1")]);
        let wcands = make_dict(&[("正經", "zing3 ging1|zing1 ging1")]);
        assert_eq!(
            token_to_jyutping_candidates("正經", &wd, &cd, &ud, Some(&wcands), None),
            vec!["zing1 ging1".to_string()]
        );
    }

    #[test]
    fn test_candidates_multi_char_oov_fallback_not_combined() {
        // Neither char is an exact word_dict/word_candidates hit, so this
        // falls through to the per-char fallback loop — candidates are NOT
        // combined across chars, matching token_to_jyutping's single result.
        let wd = make_dict(&[]);
        let cd = make_dict(&[("老", "lou5"), ("世", "sai3")]);
        let ud = UserDict::new(HashMap::new());
        let ccands = make_dict(&[("老", "lou5|lou2")]);
        assert_eq!(
            token_to_jyutping_candidates("老世", &wd, &cd, &ud, None, Some(&ccands)),
            vec!["lou5 sai3".to_string()]
        );
    }

    #[test]
    fn test_candidates_missing_sidecars_behave_like_none() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let cd = make_dict(&[]);
        let ud = UserDict::new(HashMap::new());
        assert_eq!(
            token_to_jyutping_candidates("香港", &wd, &cd, &ud, None, None),
            vec!["hoeng1 gong2".to_string()]
        );
    }
}
