use crate::tone_util::brighten_to_tone2;
use std::collections::HashMap;

/// Cantonese "AA哋" changed tone (疊字形容詞 + 哋, "rather X" / "-ish"): a
/// single-character adjective immediately reduplicated and followed by the
/// suffix 哋 has its second copy brightened to 陰上 (tone 2), and 哋 itself
/// always reads `dei2` (not its citation `dei6`) — 黃黃哋 -> wong4 wong2 dei2
/// (not wong4 wong4 dei6), 辣辣哋 -> laat6 laat2 dei2 (not laat6 laat6 dei6).
/// This is a real, independently documented Cantonese grammatical
/// construction (Matthews & Yip, *Cantonese: A Comprehensive Grammar*), not
/// a polyphone-selection bug.
///
/// Purely structural — no whitelist, unlike `crate::classifier_reduplication`:
/// "single CJK char, repeated, then 哋" is unproductive outside this
/// construction, so token adjacency alone is a strong enough signal,
/// mirroring `crate::address_sandhi`'s reasoning for its own narrower
/// "X sir" pattern. A handful of common AA哋 words (肥肥哋, 傻傻哋, 矮矮哋) are
/// already lexicalized as their own single word-dict entry with the correct
/// reading baked in — those never reach this 3-token pattern at all, so this
/// pass only fires for the combinations rime-cantonese doesn't happen to
/// list as a standalone word.
pub fn resolve_aa_dei_overrides(tokens: &[String], readings: &[String]) -> HashMap<usize, String> {
    let mut overrides = HashMap::new();
    if tokens.len() < 3 || tokens.len() != readings.len() {
        return overrides;
    }

    for i in 0..tokens.len() - 2 {
        if tokens[i].chars().count() != 1 {
            continue;
        }
        if tokens[i] != tokens[i + 1] {
            continue;
        }
        if tokens[i + 2] != "哋" {
            continue;
        }
        if let Some(sandhi) = brighten_to_tone2(&readings[i + 1]) {
            overrides.insert(i + 1, sandhi);
        }
        if let Some(sandhi) = brighten_to_tone2(&readings[i + 2]) {
            overrides.insert(i + 2, sandhi);
        }
    }

    overrides
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toks(strs: &[&str]) -> Vec<String> {
        strs.iter().map(|s| s.to_string()).collect()
    }
    fn readings(strs: &[&str]) -> Vec<String> {
        strs.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn test_yang_ping_aa_dei_brightens() {
        // 黃黃哋 -> wong4 wong2 dei2 (not wong4 wong4 dei6)
        let tokens = toks(&["黃", "黃", "哋"]);
        let r = readings(&["wong4", "wong4", "dei6"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert_eq!(overrides.get(&1), Some(&"wong2".to_string()));
        assert_eq!(overrides.get(&2), Some(&"dei2".to_string()));
        assert_eq!(overrides.len(), 2);
    }

    #[test]
    fn test_entering_tone_aa_dei_brightens() {
        // 辣辣哋 -> laat6 laat2 dei2 (陽入, still Jyutping tone digit 6)
        let tokens = toks(&["辣", "辣", "哋"]);
        let r = readings(&["laat6", "laat6", "dei6"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert_eq!(overrides.get(&1), Some(&"laat2".to_string()));
        assert_eq!(overrides.get(&2), Some(&"dei2".to_string()));
    }

    #[test]
    fn test_tone_1_adjective_only_dei_brightens() {
        // 黑黑哋 -> haak1 haak1 dei2 (adjective already tone 1, unaffected)
        let tokens = toks(&["黑", "黑", "哋"]);
        let r = readings(&["haak1", "haak1", "dei6"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert_eq!(overrides.get(&1), None);
        assert_eq!(overrides.get(&2), Some(&"dei2".to_string()));
        assert_eq!(overrides.len(), 1);
    }

    #[test]
    fn test_non_reduplicated_before_dei_unaffected() {
        let tokens = toks(&["肥", "佬", "哋"]);
        let r = readings(&["fei4", "lou2", "dei6"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_reduplication_not_followed_by_dei_unaffected() {
        let tokens = toks(&["黃", "黃", "色"]);
        let r = readings(&["wong4", "wong4", "sik1"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_multi_char_reduplicated_token_unaffected() {
        let tokens = toks(&["開心", "開心", "哋"]);
        let r = readings(&["hoi1 sam1", "hoi1 sam1", "dei6"]);
        let overrides = resolve_aa_dei_overrides(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_short_or_mismatched_input_does_not_panic() {
        assert!(resolve_aa_dei_overrides(&[], &[]).is_empty());
        assert!(
            resolve_aa_dei_overrides(&toks(&["黃", "黃"]), &readings(&["wong4", "wong4"]))
                .is_empty()
        );
        assert!(resolve_aa_dei_overrides(
            &toks(&["黃", "黃", "哋"]),
            &readings(&["wong4", "wong4"])
        )
        .is_empty());
    }
}
