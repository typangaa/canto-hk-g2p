use crate::dict::Dict;
use std::collections::HashMap;

/// Closed class of Cantonese aspect markers that can be inserted between the
/// two syllables of a separable verb-object compound (離合詞) — 緊
/// (progressive), 咗 (perfective), 過 (experiential), 開 (habitual). E.g.
/// 瞓覺 → 瞓緊覺 ("sleeping") / 瞓咗覺 ("slept"). Whether all four markers read
/// as natural for a *given* compound is a lexical/pragmatic question (e.g.
/// 瞓覺 pairs naturally with 緊/咗 but not idiomatically with 過/開 without
/// more context) — this list is the grammatical closed class itself, kept
/// general so future whitelist entries aren't artificially restricted.
const ASPECT_MARKERS: &[&str] = &["緊", "咗", "過", "開"];

/// Scans `tokens` for `[verb, aspect_marker, noun]` triples — three
/// immediately-adjacent tokens, each a single CJK character, with the middle
/// one a known aspect marker — where `verb + noun` is a known separable
/// compound in `separable_dict`. Returns the token indices whose reading
/// must be forced to that compound's own per-syllable reading (verb's index
/// -> its syllable, noun's index -> its syllable), taken straight from the
/// compound's bundled reading so it can never drift out of sync with
/// word.bin.
///
/// Only whitelisted verb+noun pairs fire — not any coincidental adjacency —
/// so false positives are bounded by what's actually in `separable_dict`.
/// Punctuation tokens (emitted separately by `segment_owned`) naturally
/// break contiguity, so a marker separated by punctuation from the verb or
/// noun never matches.
pub fn resolve_separable_overrides(
    tokens: &[String],
    separable_dict: Option<&Dict>,
) -> HashMap<usize, String> {
    let mut overrides = HashMap::new();
    let Some(dict) = separable_dict else {
        return overrides;
    };
    if tokens.len() < 3 {
        return overrides;
    }

    for i in 0..=tokens.len() - 3 {
        let (verb, marker, noun) = (&tokens[i], &tokens[i + 1], &tokens[i + 2]);
        if verb.chars().count() != 1 || noun.chars().count() != 1 {
            continue;
        }
        if !ASPECT_MARKERS.contains(&marker.as_str()) {
            continue;
        }

        let combined = format!("{verb}{noun}");
        let Some(reading) = dict.lookup(&combined) else {
            continue;
        };
        let mut parts = reading.split(' ');
        if let (Some(v_reading), Some(n_reading), None) = (parts.next(), parts.next(), parts.next())
        {
            overrides.insert(i, v_reading.to_owned());
            overrides.insert(i + 2, n_reading.to_owned());
        }
    }

    overrides
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
        let dir = std::env::temp_dir().join(format!("canto_g2p_separable_test_{nanos}"));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("test.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&out).unwrap();
        drop(f);
        Dict::load(&path).unwrap()
    }

    fn toks(strs: &[&str]) -> Vec<String> {
        strs.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn test_matches_known_separable_triple() {
        let dict = make_dict(&[("瞓覺", "fan3 gaau3")]);
        let tokens = toks(&["佢", "瞓", "緊", "覺"]);
        let overrides = resolve_separable_overrides(&tokens, Some(&dict));
        assert_eq!(overrides.get(&1), Some(&"fan3".to_string()));
        assert_eq!(overrides.get(&3), Some(&"gaau3".to_string()));
        assert_eq!(overrides.len(), 2);
    }

    #[test]
    fn test_no_match_when_marker_not_in_aspect_list() {
        let dict = make_dict(&[("瞓覺", "fan3 gaau3")]);
        // "地" is not an aspect marker.
        let tokens = toks(&["瞓", "地", "覺"]);
        let overrides = resolve_separable_overrides(&tokens, Some(&dict));
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_no_match_when_combined_word_not_in_dict() {
        let dict = make_dict(&[("瞓覺", "fan3 gaau3")]);
        // "食" + "碗" is not a whitelisted separable compound.
        let tokens = toks(&["食", "緊", "碗"]);
        let overrides = resolve_separable_overrides(&tokens, Some(&dict));
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_no_overrides_when_separable_dict_is_none() {
        let tokens = toks(&["瞓", "緊", "覺"]);
        let overrides = resolve_separable_overrides(&tokens, None);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_short_token_list_does_not_panic() {
        let dict = make_dict(&[("瞓覺", "fan3 gaau3")]);
        assert!(resolve_separable_overrides(&[], Some(&dict)).is_empty());
        assert!(resolve_separable_overrides(&toks(&["瞓"]), Some(&dict)).is_empty());
        assert!(resolve_separable_overrides(&toks(&["瞓", "緊"]), Some(&dict)).is_empty());
    }

    #[test]
    fn test_multi_char_verb_or_noun_never_matches() {
        let dict = make_dict(&[("瞓覺", "fan3 gaau3")]);
        // Multi-char tokens either side of the marker must be skipped, not
        // panic on the char-count check.
        let tokens = toks(&["瞓覺先", "緊", "覺"]);
        let overrides = resolve_separable_overrides(&tokens, Some(&dict));
        assert!(overrides.is_empty());
    }
}
