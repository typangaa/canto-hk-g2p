//! Runtime user-supplied override dictionary (`Pipeline(user_dict=...)`).
//!
//! Unlike `dict::Dict` (mmap'd, built at compile/package time), a `UserDict`
//! is small, constructed from a plain Python dict at `Pipeline` construction
//! time, and always takes priority over `word_dict`/`char_dict`/`oral_hk`.
//! It participates in segmentation exactly like `Dict::longest_prefix_match`
//! so a multi-char override (e.g. `"老世" -> "lou5 sai3"`) is not split up
//! by the default word-frequency segmenter before it ever gets to `g2p.rs`.

use std::collections::HashMap;

pub struct UserDict {
    entries: HashMap<String, String>,
    max_chars: usize,
}

impl UserDict {
    pub fn new(entries: HashMap<String, String>) -> Self {
        let max_chars = entries.keys().map(|k| k.chars().count()).max().unwrap_or(0);
        UserDict { entries, max_chars }
    }

    /// Exact key lookup.
    pub fn get(&self, key: &str) -> Option<&str> {
        self.entries.get(key).map(String::as_str)
    }

    /// Find the longest user_dict key starting at the beginning of `text`.
    /// Mirrors `dict::Dict::longest_prefix_match`'s semantics exactly, so
    /// callers can compare byte lengths directly against a `Dict` match.
    pub fn longest_prefix_match<'a>(
        &'a self,
        text: &str,
        max_chars: usize,
    ) -> Option<(usize, &'a str)> {
        if self.entries.is_empty() {
            return None;
        }
        let limit = max_chars.min(self.max_chars);
        if limit == 0 {
            return None;
        }

        let mut prefix_ends: Vec<usize> = Vec::with_capacity(limit);
        let mut chars_seen = 0usize;
        for (byte_idx, ch) in text.char_indices() {
            chars_seen += 1;
            prefix_ends.push(byte_idx + ch.len_utf8());
            if chars_seen >= limit {
                break;
            }
        }

        for i in (0..prefix_ends.len()).rev() {
            let byte_len = prefix_ends[i];
            let prefix = &text[..byte_len];
            if let Some(val) = self.entries.get(prefix) {
                return Some((byte_len, val.as_str()));
            }
        }

        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make(pairs: &[(&str, &str)]) -> UserDict {
        UserDict::new(
            pairs
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
        )
    }

    #[test]
    fn test_empty_dict() {
        let ud = UserDict::new(HashMap::new());
        assert_eq!(ud.get("你"), None);
        assert_eq!(ud.longest_prefix_match("你好", 10), None);
    }

    #[test]
    fn test_exact_get() {
        let ud = make(&[("老世", "lou5 sai3")]);
        assert_eq!(ud.get("老世"), Some("lou5 sai3"));
        assert_eq!(ud.get("老"), None);
    }

    #[test]
    fn test_longest_prefix_match_multi_char() {
        let ud = make(&[("老世", "lou5 sai3")]);
        let result = ud.longest_prefix_match("老世要求", 10);
        assert_eq!(result, Some((6, "lou5 sai3"))); // 老世 = 6 bytes
    }

    #[test]
    fn test_longest_prefix_match_no_match() {
        let ud = make(&[("老世", "lou5 sai3")]);
        assert_eq!(ud.longest_prefix_match("你好", 10), None);
    }

    #[test]
    fn test_longest_prefix_match_prefers_longer_key() {
        let ud = make(&[("行", "hong4"), ("行為", "hang4 wai4")]);
        let result = ud.longest_prefix_match("行為不檢", 10);
        assert_eq!(result, Some((6, "hang4 wai4")));
    }

    #[test]
    fn test_longest_prefix_match_max_chars_limit() {
        let ud = make(&[("行為", "hang4 wai4"), ("行", "hong4")]);
        // max_chars=1 caps the prefix search to a single character.
        let result = ud.longest_prefix_match("行為", 1);
        assert_eq!(result, Some((3, "hong4")));
    }

    #[test]
    fn test_longest_prefix_match_max_chars_zero() {
        let ud = make(&[("行", "hong4")]);
        assert_eq!(ud.longest_prefix_match("行", 0), None);
    }
}
