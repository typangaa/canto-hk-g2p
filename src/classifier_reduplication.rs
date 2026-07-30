use crate::dict::Dict;
use crate::tone_util::brighten_to_tone2;
use std::collections::HashMap;

/// Cantonese "reduplicated classifier" changed tone (量詞疊字表達「每個/全
/// 部」): a whitelisted classifier or common distributive noun, immediately
/// reduplicated (XX), expresses "every X" and brightens its second copy to
/// 陰上 (tone 2) — 個個 -> go3 go2 (not go3 go3), 日日 -> jat6 jat2 (not jat6
/// jat6), 人人 -> jan4 jan2 (not jan4 jan4). This is a real, independently
/// documented Cantonese construction (Matthews & Yip, *Cantonese: A
/// Comprehensive Grammar*), distinct from unrelated reduplication that does
/// NOT undergo this shift (剛剛 "just now", 常常 "often" keep their citation
/// tone) — hence the whitelist gate, unlike `crate::aa_dei_sandhi`'s purely
/// structural pattern.
///
/// `classifiers` (the `classifier_words.bin` sidecar, built from
/// `data/classifier_words.tsv`) is a deliberately small, evidence-based
/// pilot list — see that file's header for what it takes to add a word.
/// `None` if the sidecar is missing from the data directory — older/custom
/// data dirs still work, this override pass then simply never fires.
pub fn resolve_classifier_reduplication_overrides(
    tokens: &[String],
    readings: &[String],
    classifiers: Option<&Dict>,
) -> HashMap<usize, String> {
    let mut overrides = HashMap::new();
    let Some(classifiers) = classifiers else {
        return overrides;
    };
    if tokens.len() < 2 || tokens.len() != readings.len() {
        return overrides;
    }

    for i in 0..tokens.len() - 1 {
        if tokens[i].chars().count() != 1 {
            continue;
        }
        if tokens[i] != tokens[i + 1] {
            continue;
        }
        if classifiers.lookup(&tokens[i]).is_none() {
            continue;
        }
        if let Some(sandhi) = brighten_to_tone2(&readings[i + 1]) {
            overrides.insert(i + 1, sandhi);
        }
    }

    overrides
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn toks(strs: &[&str]) -> Vec<String> {
        strs.iter().map(|s| s.to_string()).collect()
    }
    fn readings(strs: &[&str]) -> Vec<String> {
        strs.iter().map(|s| s.to_string()).collect()
    }

    fn make_dict(entries: &[&str]) -> Dict {
        let mut sorted: Vec<&str> = entries.to_vec();
        sorted.sort();

        let mut pool: Vec<u8> = Vec::new();
        let mut offsets: Vec<(u32, u16, u32, u16)> = Vec::new();
        for key in &sorted {
            let ks = pool.len() as u32;
            let kl = key.len() as u16;
            pool.extend_from_slice(key.as_bytes());
            let vs = pool.len() as u32;
            let vl = key.len() as u16;
            pool.extend_from_slice(key.as_bytes());
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

        let dir = std::env::temp_dir().join(format!(
            "canto_g2p_classifier_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("classifier_words.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&out).unwrap();
        Dict::load(&path).unwrap()
    }

    #[test]
    fn test_whitelisted_classifier_reduplication_brightens() {
        // 個個 -> go3 go2 (not go3 go3)
        let dict = make_dict(&["個", "日", "人"]);
        let tokens = toks(&["個", "個"]);
        let r = readings(&["go3", "go3"]);
        let overrides = resolve_classifier_reduplication_overrides(&tokens, &r, Some(&dict));
        assert_eq!(overrides.get(&1), Some(&"go2".to_string()));
        assert_eq!(overrides.len(), 1);
    }

    #[test]
    fn test_entering_tone_classifier_brightens() {
        // 日日 -> jat6 jat2 (陽入, still Jyutping tone digit 6)
        let dict = make_dict(&["日"]);
        let tokens = toks(&["日", "日"]);
        let r = readings(&["jat6", "jat6"]);
        let overrides = resolve_classifier_reduplication_overrides(&tokens, &r, Some(&dict));
        assert_eq!(overrides.get(&1), Some(&"jat2".to_string()));
    }

    #[test]
    fn test_non_whitelisted_reduplication_unaffected() {
        // 常常 ("often") — reduplication but not a classifier, no shift.
        let dict = make_dict(&["個", "日"]);
        let tokens = toks(&["常", "常"]);
        let r = readings(&["soeng4", "soeng4"]);
        let overrides = resolve_classifier_reduplication_overrides(&tokens, &r, Some(&dict));
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_no_sidecar_never_fires() {
        let tokens = toks(&["個", "個"]);
        let r = readings(&["go3", "go3"]);
        let overrides = resolve_classifier_reduplication_overrides(&tokens, &r, None);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_non_reduplicated_classifier_unaffected() {
        let dict = make_dict(&["個"]);
        let tokens = toks(&["個", "人"]);
        let r = readings(&["go3", "jan4"]);
        let overrides = resolve_classifier_reduplication_overrides(&tokens, &r, Some(&dict));
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_short_or_mismatched_input_does_not_panic() {
        let dict = make_dict(&["個"]);
        assert!(resolve_classifier_reduplication_overrides(&[], &[], Some(&dict)).is_empty());
        assert!(resolve_classifier_reduplication_overrides(
            &toks(&["個"]),
            &readings(&["go3"]),
            Some(&dict)
        )
        .is_empty());
        assert!(resolve_classifier_reduplication_overrides(
            &toks(&["個", "個"]),
            &readings(&["go3"]),
            Some(&dict)
        )
        .is_empty());
    }
}
