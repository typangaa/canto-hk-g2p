/// Word segmenter: longest-match + word-frequency DP over word dict (Phase 2).
/// Phase 0 stub: yield one segment per Unicode scalar.
pub fn segment(text: &str) -> Vec<String> {
    text.chars().map(|c| c.to_string()).collect()
}
