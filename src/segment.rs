use crate::dict::Dict;

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
/// * CJK runs  → longest-match segmentation over `word_dict`
/// * Latin runs (ASCII a-z A-Z 0-9) → kept as a single token each
/// * Other chars → non-whitespace emitted as individual tokens (punctuation),
///   whitespace silently dropped
pub fn segment_owned(text: &str, word_dict: &Dict) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    let mut buf = String::new();
    let mut current = RunKind::Other;

    for ch in text.chars() {
        let kind = run_kind(ch);

        if kind == current && kind != RunKind::Other {
            buf.push(ch);
        } else {
            flush_run(&buf, current, word_dict, &mut tokens);
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

    flush_run(&buf, current, word_dict, &mut tokens);
    tokens
}

fn flush_run(buf: &str, kind: RunKind, word_dict: &Dict, tokens: &mut Vec<String>) {
    if buf.is_empty() {
        return;
    }
    match kind {
        RunKind::Cjk => segment_cjk(buf, word_dict, tokens),
        RunKind::Latin => tokens.push(buf.to_owned()),
        RunKind::Other => {}
    }
}

fn segment_cjk(text: &str, word_dict: &Dict, tokens: &mut Vec<String>) {
    let mut remaining = text;
    while !remaining.is_empty() {
        if let Some((byte_len, _)) = word_dict.longest_prefix_match(remaining, MAX_WORD_CHARS) {
            tokens.push(remaining[..byte_len].to_owned());
            remaining = &remaining[byte_len..];
        } else {
            let ch = remaining.chars().next().unwrap();
            tokens.push(ch.to_string());
            remaining = &remaining[ch.len_utf8()..];
        }
    }
}
