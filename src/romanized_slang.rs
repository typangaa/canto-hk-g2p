use crate::dict::Dict;

/// Replaces ASCII/numeral leetspeak spellings of Cantonese slang (e.g. "on9"
/// for 戇鳩, see `data/romanized_slang.tsv`) with their canonical CJK
/// spelling, BEFORE any other normalization runs. This has to happen ahead
/// of `normalizer::normalize()`'s number-reading rules — otherwise a bare
/// trailing digit like the "9" in "on9" gets read as the cardinal number
/// nine before this pass ever sees it, and the surrounding letters are
/// already a separate token by the time segmentation splits Latin from CJK
/// runs (see `segment.rs`).
///
/// Matches whole ASCII-alnum runs only (word-boundary gated by the
/// surrounding non-ASCII-alnum characters), case-insensitively, so "on9"
/// matches but "conan9" or "on99" do not. Returns the input unchanged
/// (allocation-free) when `dict` is `None` (older/custom data dirs without
/// `romanized_slang.bin` keep working) or no run in the text matches.
pub fn substitute(text: &str, dict: Option<&Dict>) -> String {
    let Some(dict) = dict else {
        return text.to_owned();
    };

    let mut out = String::with_capacity(text.len());
    let mut run = String::new();

    for ch in text.chars() {
        if ch.is_ascii_alphanumeric() {
            run.push(ch);
        } else {
            flush_run(&run, dict, &mut out);
            run.clear();
            out.push(ch);
        }
    }
    flush_run(&run, dict, &mut out);

    out
}

fn flush_run(run: &str, dict: &Dict, out: &mut String) {
    if run.is_empty() {
        return;
    }
    let lower = run.to_ascii_lowercase();
    match dict.lookup(&lower) {
        Some(canonical) => out.push_str(canonical),
        None => out.push_str(run),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
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
        let dir = std::env::temp_dir().join(format!("canto_g2p_slang_test_{nanos}"));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&out).unwrap();
        drop(f);
        Dict::load(&path).unwrap()
    }

    #[test]
    fn test_matches_known_slang_form() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        assert_eq!(substitute("on9", Some(&dict)), "戇鳩");
    }

    #[test]
    fn test_case_insensitive() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        assert_eq!(substitute("ON9", Some(&dict)), "戇鳩");
        assert_eq!(substitute("On9", Some(&dict)), "戇鳩");
    }

    #[test]
    fn test_word_boundary_gated() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        // "on99" and "conan9" are different whole runs, not substring hits.
        assert_eq!(substitute("on99", Some(&dict)), "on99");
        assert_eq!(substitute("conan9", Some(&dict)), "conan9");
    }

    #[test]
    fn test_surrounded_by_other_text() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        assert_eq!(substitute("佢好on9啊", Some(&dict)), "佢好戇鳩啊");
    }

    #[test]
    fn test_no_dict_returns_input_unchanged() {
        assert_eq!(substitute("on9", None), "on9");
    }

    #[test]
    fn test_no_match_leaves_run_untouched() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        assert_eq!(substitute("hello123", Some(&dict)), "hello123");
    }

    #[test]
    fn test_empty_text() {
        let dict = make_dict(&[("on9", "戇鳩")]);
        assert_eq!(substitute("", Some(&dict)), "");
    }
}
