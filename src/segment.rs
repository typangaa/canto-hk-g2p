use crate::dict::Dict;
use crate::user_dict::UserDict;

const MAX_WORD_CHARS: usize = 10;

#[derive(PartialEq, Clone, Copy)]
enum RunKind {
    Cjk,   // CJK unified ideographs — segment via dict
    Latin, // ASCII letters/digits — keep as one token
    Other, // spaces, punctuation — emit non-whitespace chars individually
}

fn run_kind(c: char) -> RunKind {
    match c as u32 {
        0x4E00..=0x9FFF       // CJK Unified Ideographs
        | 0x3400..=0x4DBF     // CJK Extension A
        | 0x20000..=0x2A6DF   // CJK Extension B
        | 0xF900..=0xFAFF     // CJK Compatibility Ideographs
        => RunKind::Cjk,
        0x41..=0x5A           // A-Z
        | 0x61..=0x7A         // a-z
        | 0x30..=0x39         // 0-9
        => RunKind::Latin,
        _ => RunKind::Other,
    }
}

/// Segment `text` into tokens.
///
/// * CJK runs  → longest-match segmentation over `word_dict` ∪ `user_dict`
///   (a `user_dict` entry wins ties against an equal-length `word_dict` match,
///   so an override is never silently outranked by the shipped dictionary)
/// * Latin runs (ASCII a-z A-Z 0-9) → kept as a single token each
/// * Other chars → non-whitespace emitted as individual tokens (punctuation),
///   whitespace silently dropped
pub fn segment_owned(text: &str, word_dict: &Dict, user_dict: &UserDict) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    let mut buf = String::new();
    let mut current = RunKind::Other;

    for ch in text.chars() {
        let kind = run_kind(ch);

        if kind == current && kind != RunKind::Other {
            buf.push(ch);
        } else {
            flush_run(&buf, current, word_dict, user_dict, &mut tokens);
            buf.clear();

            if kind == RunKind::Other {
                if !ch.is_whitespace() {
                    tokens.push(ch.to_string());
                }
                current = RunKind::Other;
            } else {
                buf.push(ch);
                current = kind;
            }
        }
    }

    flush_run(&buf, current, word_dict, user_dict, &mut tokens);
    tokens
}

fn flush_run(
    buf: &str,
    kind: RunKind,
    word_dict: &Dict,
    user_dict: &UserDict,
    tokens: &mut Vec<String>,
) {
    if buf.is_empty() {
        return;
    }
    match kind {
        RunKind::Cjk => segment_cjk(buf, word_dict, user_dict, tokens),
        RunKind::Latin => tokens.push(buf.to_owned()),
        RunKind::Other => {}
    }
}

fn segment_cjk(text: &str, word_dict: &Dict, user_dict: &UserDict, tokens: &mut Vec<String>) {
    let mut remaining = text;
    while !remaining.is_empty() {
        let word_match = word_dict.longest_prefix_match(remaining, MAX_WORD_CHARS);
        let user_match = user_dict.longest_prefix_match(remaining, MAX_WORD_CHARS);

        // user_dict wins ties against word_dict so an override is never
        // outranked by a shipped word of the same length.
        let byte_len = match (word_match, user_match) {
            (Some((wl, _)), Some((ul, _))) if ul >= wl => Some(ul),
            (Some((wl, _)), _) => Some(wl),
            (None, Some((ul, _))) => Some(ul),
            (None, None) => None,
        };

        if let Some(byte_len) = byte_len {
            tokens.push(remaining[..byte_len].to_owned());
            remaining = &remaining[byte_len..];
        } else {
            let ch = remaining.chars().next().unwrap();
            tokens.push(ch.to_string());
            remaining = &remaining[ch.len_utf8()..];
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::io::Write;

    /// Build a minimal well-formed CJYP v1 `.bin` file in memory and load it.
    /// `pairs` need not be pre-sorted — this helper sorts them.
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
        let dir = std::env::temp_dir().join(format!("canto_g2p_segment_test_{nanos}"));
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
    fn test_segment_without_user_dict_unchanged() {
        let wd = make_dict(&[("香港", "hoeng1 gong2"), ("香", "hoeng1"), ("港", "gong2")]);
        let tokens = segment_owned("香港", &wd, &UserDict::new(HashMap::new()));
        assert_eq!(tokens, vec!["香港".to_string()]);
    }

    #[test]
    fn test_user_dict_multi_char_not_split() {
        // "老世" is not in word_dict at all — without user_dict it would be
        // split into two single-char tokens ("老", "世").
        let wd = make_dict(&[("老", "lou5"), ("世", "sai3")]);
        let ud = user(&[("老世", "lou5 sai3")]);
        let tokens = segment_owned("老世要求", &wd, &ud);
        assert_eq!(tokens[0], "老世");
    }

    #[test]
    fn test_user_dict_wins_tie_against_word_dict() {
        // Both dicts have a 2-char entry for "行為" — user_dict must win.
        let wd = make_dict(&[("行為", "haang4 wai4")]);
        let ud = user(&[("行為", "hang4 wai4")]);
        let tokens = segment_owned("行為", &wd, &ud);
        assert_eq!(tokens, vec!["行為".to_string()]);
        // Segmentation only decides token boundaries — the value itself
        // (user_dict wins on lookup) is resolved later in g2p.rs.
    }

    #[test]
    fn test_user_dict_shorter_than_word_dict_loses() {
        // word_dict has a 3-char match, user_dict only overrides the 2-char
        // prefix — word_dict's longer match should win.
        let wd = make_dict(&[("銀行家", "ngan4 hong4 gaa1")]);
        let ud = user(&[("銀行", "ngan4 hong4")]);
        let tokens = segment_owned("銀行家", &wd, &ud);
        assert_eq!(tokens, vec!["銀行家".to_string()]);
    }

    #[test]
    fn test_empty_user_dict_no_effect() {
        let wd = make_dict(&[("香港", "hoeng1 gong2")]);
        let tokens = segment_owned("香港", &wd, &UserDict::new(HashMap::new()));
        assert_eq!(tokens, vec!["香港".to_string()]);
    }
}
