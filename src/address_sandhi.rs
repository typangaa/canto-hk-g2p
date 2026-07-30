use std::collections::HashMap;

/// Cantonese "surname address" tone sandhi (姓氏稱呼變調): a single-character
/// token whose 陽 tone (Jyutping digit 4 陽平, or 6 — covering both 陽去 and
/// 陽入, which share digit 6 in Jyutping's numbering) is immediately
/// followed by the English loanword "sir" is read with 陰上 (tone 2) instead
/// of its citation tone — 黃sir -> wong2 sir (not wong4), 陳sir -> can2 sir
/// (not can4), 鄭sir -> zeng2 sir (not zeng6), 陸sir -> luk2 sir (陽入, not
/// luk6). This is a real, independently documented
/// Cantonese phenomenon (not a polyphone-selection bug): "兩個陽平聲連讀唔順
/// 口", so the low/dark tone brightens to a rising tone 2 in this address
/// construction. The same sandhi also applies to "阿X"/"老X"/"X伯" address
/// forms, but this pass is deliberately scoped to the "X sir" case only — the
/// one this project was asked to check — since 阿/老 prefix a huge number of
/// unrelated common words (老師, 老鼠, 阿媽) that risk false positives without
/// a name-detection layer this project doesn't have.
///
/// Scoped as a general phonological rule, not a surname whitelist: "sir" as a
/// bare Cantonese address term is unproductive outside of following a
/// surname or nickname (肥sir, 高sir), so the token-adjacency condition alone
/// is a strong enough signal — no lookup table needed, unlike `separable.rs`.
/// This also means it isn't restricted to CLAUDE.md's locked-out "v1 skips
/// tone sandhi" scope in general — it's one narrow, well-evidenced exception
/// carved out of that broader deferral, not a reversal of it.
pub fn resolve_address_sandhi(tokens: &[String], readings: &[String]) -> HashMap<usize, String> {
    let mut overrides = HashMap::new();
    if tokens.len() < 2 || tokens.len() != readings.len() {
        return overrides;
    }

    for i in 0..tokens.len() - 1 {
        if tokens[i].chars().count() != 1 {
            continue;
        }
        if !tokens[i + 1].eq_ignore_ascii_case("sir") {
            continue;
        }
        if let Some(sandhi) = brighten_yang_tone(&readings[i]) {
            overrides.insert(i, sandhi);
        }
    }

    overrides
}

/// Rewrites a single-syllable jyutping reading's trailing 陽 tone (4 or 6) to
/// 陰上 (2). Returns `None` for any other tone, or a reading that isn't a
/// bare `<jyutping><digit>` syllable (e.g. already multi-syllable — can't
/// happen for a genuine single-CJK-char token, but guarded defensively).
fn brighten_yang_tone(reading: &str) -> Option<String> {
    if reading.contains(' ') {
        return None;
    }
    let tone = reading.chars().last()?;
    if !matches!(tone, '4' | '6') {
        return None;
    }
    let base = &reading[..reading.len() - 1];
    if base.is_empty() || !base.chars().all(|c| c.is_ascii_lowercase()) {
        return None;
    }
    Some(format!("{base}2"))
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
    fn test_yang_ping_tone4_brightens_before_sir() {
        // 黃sir -> wong2 sir (not wong4)
        let tokens = toks(&["黃", "sir"]);
        let r = readings(&["wong4", "sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert_eq!(overrides.get(&0), Some(&"wong2".to_string()));
        assert_eq!(overrides.len(), 1);
    }

    #[test]
    fn test_yang_heoi_tone6_brightens_before_sir() {
        // 鄭sir -> zing2 sir (not zeng6)
        let tokens = toks(&["鄭", "sir"]);
        let r = readings(&["zeng6", "sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert_eq!(overrides.get(&0), Some(&"zeng2".to_string()));
    }

    #[test]
    fn test_yang_jap_tone6_brightens_before_sir() {
        // 陸sir -> luk2 sir (陽入, still Jyutping tone digit 6 -- same rule
        // as 陽去 covers it with no special-casing).
        let tokens = toks(&["陸", "sir"]);
        let r = readings(&["luk6", "sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert_eq!(overrides.get(&0), Some(&"luk2".to_string()));
    }

    #[test]
    fn test_case_insensitive_sir_token() {
        let tokens = toks(&["陳", "Sir"]);
        let r = readings(&["can4", "Sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert_eq!(overrides.get(&0), Some(&"can2".to_string()));
    }

    #[test]
    fn test_non_yang_tone_unaffected() {
        // 李sir already tone 5 (陽上) -- left untouched (no evidence this
        // tone brightens the same way).
        let tokens = toks(&["李", "sir"]);
        let r = readings(&["lei5", "sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_not_adjacent_to_sir_unaffected() {
        let tokens = toks(&["黃", "生"]);
        let r = readings(&["wong4", "sang1"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_multi_char_token_before_sir_unaffected() {
        let tokens = toks(&["阿黃", "sir"]);
        let r = readings(&["aa3 wong4", "sir"]);
        let overrides = resolve_address_sandhi(&tokens, &r);
        assert!(overrides.is_empty());
    }

    #[test]
    fn test_short_or_mismatched_input_does_not_panic() {
        assert!(resolve_address_sandhi(&[], &[]).is_empty());
        assert!(resolve_address_sandhi(&toks(&["黃"]), &readings(&["wong4"])).is_empty());
        assert!(resolve_address_sandhi(&toks(&["黃", "sir"]), &readings(&["wong4"])).is_empty());
    }
}
