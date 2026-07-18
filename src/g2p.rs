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
}
