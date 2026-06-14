use crate::dict::Dict;

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
///   2. word_dict exact match  (catches multi-char words + polyphone resolution)
///   3. char_dict per-character fallback  (single-char OOV)
pub fn token_to_jyutping<'a>(token: &str, word_dict: &'a Dict, char_dict: &'a Dict) -> String {
    // 1. Non-CJK → passthrough (English, punctuation, digits)
    if !is_cjk(token) {
        return token.to_owned();
    }

    // 2. Exact word lookup (CJK tokens only)
    if let Some(jp) = word_dict.lookup(token) {
        return jp.to_owned();
    }

    // 3. CJK char-by-char fallback via char_dict
    let mut result = String::new();
    for ch in token.chars() {
        let s = ch.to_string();
        if let Some(jp) = word_dict.lookup(&s).or_else(|| char_dict.lookup(&s)) {
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
