/// Shared "brighten to 陰上 (tone 2)" primitive used by several Cantonese
/// changed-tone (變音) rules that all brighten toward the same target tone:
/// reduplicated-classifier "every X" sandhi (個個, 日日 — see
/// `crate::classifier_reduplication`) and AA哋 "rather X" sandhi (黃黃哋,
/// 辣辣哋 — see `crate::aa_dei_sandhi`). Tones 3, 4, 5, 6 brighten to 2; tones
/// 1 and 2 are left unchanged (already at or above the target — no evidence
/// they shift further in these constructions).
///
/// `crate::address_sandhi` has its own narrower sibling of this same
/// primitive (tones 4/6 only, scoped to the "X sir" address construction,
/// where no evidence supports tones 3/5 brightening the same way) — kept
/// separate rather than generalized, so broadening this one never silently
/// changes that rule's behavior.
pub fn brighten_to_tone2(reading: &str) -> Option<String> {
    if reading.contains(' ') {
        return None;
    }
    let tone = reading.chars().last()?;
    if !matches!(tone, '3' | '4' | '5' | '6') {
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

    #[test]
    fn test_brightens_tone_3_4_5_6() {
        assert_eq!(brighten_to_tone2("go3"), Some("go2".to_string()));
        assert_eq!(brighten_to_tone2("wong4"), Some("wong2".to_string()));
        assert_eq!(brighten_to_tone2("lei5"), Some("lei2".to_string()));
        assert_eq!(brighten_to_tone2("zeng6"), Some("zeng2".to_string()));
    }

    #[test]
    fn test_tone_1_and_2_unaffected() {
        assert_eq!(brighten_to_tone2("zoeng1"), None);
        assert_eq!(brighten_to_tone2("so2"), None);
    }

    #[test]
    fn test_multi_syllable_rejected() {
        assert_eq!(brighten_to_tone2("fan3 gaau3"), None);
    }

    #[test]
    fn test_malformed_input_does_not_panic() {
        assert_eq!(brighten_to_tone2(""), None);
        assert_eq!(brighten_to_tone2("3"), None);
        assert_eq!(brighten_to_tone2("Sir"), None);
    }
}
