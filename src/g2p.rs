/// G2P core: mmap dict lookup → char fallback → English passthrough (Phase 2).
/// Phase 0 stub: return token unchanged.
pub fn token_to_jyutping(token: &str) -> String {
    token.to_owned()
}
