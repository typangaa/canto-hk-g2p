use crate::dict::Dict;
use crate::user_dict::UserDict;
use crate::{g2p, normalizer, segment, separable};
use rayon::prelude::*;
use std::collections::HashMap;
use std::path::PathBuf;

pub struct Pipeline {
    word_dict: Dict,
    char_dict: Dict,
    user_dict: UserDict,
    /// Sparse rank-ordered candidate readings, only present for keys with
    /// 2+ known readings. `None` if the sidecar `.bin` file is missing from
    /// the data directory — older/custom data dirs still work,
    /// `convert_candidates()` just reports no known ambiguity anywhere.
    word_candidates: Option<Dict>,
    char_candidates: Option<Dict>,
    /// Categorical confidence tag per candidates key ("ranked" | "tied").
    /// `None` if the sidecar `.bin` is missing — an ambiguous token then
    /// defaults to `"tied"` (the conservative assumption: no real
    /// preference signal).
    word_candidates_confidence: Option<Dict>,
    char_candidates_confidence: Option<Dict>,
    /// Full-coverage source tag per word_dict/char_dict key (which upstream
    /// layer — rime / tojyutping / tojyutping_tiebreak / oral_hk / unihan —
    /// produced that entry). `None` if the sidecar `.bin` is missing — a
    /// dict hit then reports source `"unknown"`.
    word_source: Option<Dict>,
    char_source: Option<Dict>,
    /// Whitelist of separable verb-object compounds (離合詞, e.g. 瞓覺) that
    /// can be split by a closed-class aspect marker (緊/咗/過/開) in real
    /// speech (瞓緊覺). `None` if `separable.bin` is missing from the data
    /// directory — older/custom data dirs still work, this override pass
    /// then simply never fires.
    separable: Option<Dict>,
    pub punc_norm: bool,
}

pub fn default_data_dir() -> PathBuf {
    // Look for data/ next to the compiled binary, then fall back to cwd/data/
    let exe = std::env::current_exe().unwrap_or_default();
    let candidate = exe
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .join("data");
    if candidate.exists() {
        return candidate;
    }
    PathBuf::from("data")
}

impl Default for Pipeline {
    fn default() -> Self {
        Self::new()
    }
}

impl Pipeline {
    /// Create a Pipeline loading dict files from the default data/ directory.
    /// Punctuation normalisation is enabled by default.
    pub fn new() -> Self {
        Self::new_with_opts(true)
    }

    /// Create a Pipeline with explicit options.
    pub fn new_with_opts(punc_norm: bool) -> Self {
        let data_dir = default_data_dir();
        Self::from_dir_opts(&data_dir, punc_norm).unwrap_or_else(|e| {
            panic!("canto-g2p: failed to load dicts from {:?}: {}", data_dir, e)
        })
    }

    /// Create a Pipeline from a custom directory containing word.bin and char.bin.
    pub fn from_dir(dir: &std::path::Path) -> Result<Self, Box<dyn std::error::Error>> {
        Self::from_dir_opts(dir, true)
    }

    pub fn from_dir_opts(
        dir: &std::path::Path,
        punc_norm: bool,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        Self::from_dir_opts_with_user_dict(dir, punc_norm, HashMap::new())
    }

    /// Create a Pipeline from a custom directory, with a runtime override
    /// dictionary layered on top of word_dict/char_dict (highest priority).
    pub fn from_dir_opts_with_user_dict(
        dir: &std::path::Path,
        punc_norm: bool,
        user_dict: HashMap<String, String>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let word_dict = Dict::load(&dir.join("word.bin"))?;
        let char_dict = Dict::load(&dir.join("char.bin"))?;
        let word_candidates = Dict::load(&dir.join("word_candidates.bin")).ok();
        let char_candidates = Dict::load(&dir.join("char_candidates.bin")).ok();
        let word_candidates_confidence =
            Dict::load(&dir.join("word_candidates_confidence.bin")).ok();
        let char_candidates_confidence =
            Dict::load(&dir.join("char_candidates_confidence.bin")).ok();
        let word_source = Dict::load(&dir.join("word_source.bin")).ok();
        let char_source = Dict::load(&dir.join("char_source.bin")).ok();
        let separable = Dict::load(&dir.join("separable.bin")).ok();
        Ok(Pipeline {
            word_dict,
            char_dict,
            user_dict: UserDict::new(user_dict),
            word_candidates,
            char_candidates,
            word_candidates_confidence,
            char_candidates_confidence,
            word_source,
            char_source,
            separable,
            punc_norm,
        })
    }

    fn tokens_for(&self, text: &str) -> Vec<String> {
        let pre = if self.punc_norm {
            normalizer::punc_norm(text)
        } else {
            text.to_owned()
        };
        let normalized = normalizer::normalize(&pre);
        segment::segment_owned(&normalized, &self.word_dict, &self.user_dict)
    }

    /// Resolve a single token, or short-circuit to a `separable_compound`
    /// override (see `crate::separable`) when `override_reading` is `Some`.
    fn resolve(&self, token: &str, override_reading: Option<&str>) -> g2p::Resolution {
        if let Some(reading) = override_reading {
            return g2p::Resolution {
                candidates: vec![reading.to_owned()],
                confidence: "certain".to_owned(),
                source: "separable_compound".to_owned(),
            };
        }
        g2p::resolve_token(
            token,
            &self.word_dict,
            &self.char_dict,
            &self.user_dict,
            self.word_candidates.as_ref(),
            self.char_candidates.as_ref(),
            self.word_candidates_confidence.as_ref(),
            self.char_candidates_confidence.as_ref(),
            self.word_source.as_ref(),
            self.char_source.as_ref(),
        )
    }

    pub fn convert(&self, text: &str) -> String {
        if text.is_empty() {
            return String::new();
        }
        let tokens = self.tokens_for(text);
        let overrides = separable::resolve_separable_overrides(&tokens, self.separable.as_ref());
        tokens
            .iter()
            .enumerate()
            .map(|(idx, tok)| {
                overrides.get(&idx).cloned().unwrap_or_else(|| {
                    g2p::token_to_jyutping(tok, &self.word_dict, &self.char_dict, &self.user_dict)
                })
            })
            .collect::<Vec<_>>()
            .join(" ")
    }

    pub fn convert_batch(&self, texts: &[String]) -> Vec<String> {
        texts.par_iter().map(|t| self.convert(t)).collect()
    }

    /// Convert text to a list of (token, jyutping, lang, confidence, source)
    /// tuples. `lang`: `"yue"` = Cantonese CJK, `"en"` = Latin/English,
    /// `"punct"` = punctuation/symbol. `jyutping` is always the rank-0
    /// (most-likely) reading — see `convert_candidates()` for the full
    /// rank-ordered candidate list. `confidence`/`source` are described on
    /// `convert_candidates()`.
    pub fn convert_detailed(&self, text: &str) -> Vec<(String, String, String, String, String)> {
        if text.is_empty() {
            return vec![];
        }
        let tokens = self.tokens_for(text);
        let overrides = separable::resolve_separable_overrides(&tokens, self.separable.as_ref());
        tokens
            .into_iter()
            .enumerate()
            .map(|(idx, tok)| {
                let r = self.resolve(&tok, overrides.get(&idx).map(String::as_str));
                let lang = classify_lang(&tok).to_owned();
                (tok, r.candidates[0].clone(), lang, r.confidence, r.source)
            })
            .collect()
    }

    /// Rayon-parallel batch sibling of `convert_detailed()` — same per-text
    /// output shape, one `Vec` per input text.
    #[allow(clippy::type_complexity)]
    pub fn convert_detailed_batch(
        &self,
        texts: &[String],
    ) -> Vec<Vec<(String, String, String, String, String)>> {
        texts.par_iter().map(|t| self.convert_detailed(t)).collect()
    }

    /// Convert text to a list of (token, candidate_readings, lang,
    /// confidence, source) tuples.
    ///
    /// `candidate_readings` is rank-ordered (most-likely first); it has more
    /// than one entry only when the token (or, for OOV single chars, the
    /// character) has 2+ known readings in the bundled Candidates API data.
    /// Everything else — unambiguous words, English, punctuation, and OOV
    /// multi-char fallback tokens — reports a single-item list, exactly the
    /// reading `convert()` would produce for that token.
    ///
    /// `confidence` is `"certain"` (no ambiguity), `"ranked"` (2+ candidates
    /// ordered by ToJyutping's own context-aware ranking — a real
    /// preference signal), or `"tied"` (2+ candidates, but the order is
    /// rime-cantonese's raw arbitrary tie-break — no real preference
    /// signal; also the default when the confidence sidecar has no entry
    /// for an ambiguous token). No numeric probability is exposed by
    /// design — neither ToJyutping's trie nor rime-cantonese's tied
    /// readings carry real frequency data, so a float score would be
    /// fabricated (see CHANGELOG).
    ///
    /// `source` names the data layer that produced `candidate_readings[0]`:
    /// `"rime"`, `"tojyutping"` (exact trie hit), `"tojyutping_tiebreak"`
    /// (rime tie resolved via ToJyutping's context segmentation, v1.7.1),
    /// `"oral_hk"` (hand-curated override), `"unihan"` (char-only
    /// fallback), `"user_dict"` (caller override — always `"certain"` too,
    /// since an override is a final decision), `"passthrough"` (non-CJK),
    /// `"char_fallback"` (OOV multi-char token, architecturally
    /// unreachable via real segmenter output), `"unresolved"` (truly
    /// unknown char), or `"unknown"` (source sidecar missing/no entry).
    pub fn convert_candidates(
        &self,
        text: &str,
    ) -> Vec<(String, Vec<String>, String, String, String)> {
        if text.is_empty() {
            return vec![];
        }
        let tokens = self.tokens_for(text);
        let overrides = separable::resolve_separable_overrides(&tokens, self.separable.as_ref());
        tokens
            .into_iter()
            .enumerate()
            .map(|(idx, tok)| {
                let r = self.resolve(&tok, overrides.get(&idx).map(String::as_str));
                let lang = classify_lang(&tok).to_owned();
                (tok, r.candidates, lang, r.confidence, r.source)
            })
            .collect()
    }

    /// Rayon-parallel batch sibling of `convert_candidates()` — same
    /// per-text output shape, one `Vec` per input text.
    #[allow(clippy::type_complexity)]
    pub fn convert_candidates_batch(
        &self,
        texts: &[String],
    ) -> Vec<Vec<(String, Vec<String>, String, String, String)>> {
        texts
            .par_iter()
            .map(|t| self.convert_candidates(t))
            .collect()
    }
}

fn classify_lang(token: &str) -> &'static str {
    if token.chars().any(|c| {
        matches!(c as u32,
            0x4E00..=0x9FFF | 0x3400..=0x4DBF | 0x20000..=0x2A6DF | 0xF900..=0xFAFF)
    }) {
        return "yue";
    }
    if token
        .chars()
        .all(|c| matches!(c as u32, 0x41..=0x5A | 0x61..=0x7A | 0x30..=0x39))
    {
        return "en";
    }
    "punct"
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn write_bin(path: &std::path::Path, pairs: &[(&str, &str)]) {
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

        let mut f = std::fs::File::create(path).unwrap();
        f.write_all(&out).unwrap();
    }

    /// Build a temp data dir with word.bin/char.bin and any of the optional
    /// sidecars (candidates / confidence / source).
    #[allow(clippy::too_many_arguments)]
    fn make_data_dir(
        word: &[(&str, &str)],
        chars: &[(&str, &str)],
        word_candidates: Option<&[(&str, &str)]>,
        char_candidates: Option<&[(&str, &str)]>,
    ) -> PathBuf {
        make_data_dir_full(
            word,
            chars,
            word_candidates,
            char_candidates,
            None,
            None,
            None,
            None,
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn make_data_dir_full(
        word: &[(&str, &str)],
        chars: &[(&str, &str)],
        word_candidates: Option<&[(&str, &str)]>,
        char_candidates: Option<&[(&str, &str)]>,
        word_candidates_confidence: Option<&[(&str, &str)]>,
        char_candidates_confidence: Option<&[(&str, &str)]>,
        word_source: Option<&[(&str, &str)]>,
        char_source: Option<&[(&str, &str)]>,
    ) -> PathBuf {
        use std::time::{SystemTime, UNIX_EPOCH};
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("canto_g2p_pipeline_test_{nanos}"));
        std::fs::create_dir_all(&dir).unwrap();

        write_bin(&dir.join("word.bin"), word);
        write_bin(&dir.join("char.bin"), chars);
        if let Some(wc) = word_candidates {
            write_bin(&dir.join("word_candidates.bin"), wc);
        }
        if let Some(cc) = char_candidates {
            write_bin(&dir.join("char_candidates.bin"), cc);
        }
        if let Some(wcc) = word_candidates_confidence {
            write_bin(&dir.join("word_candidates_confidence.bin"), wcc);
        }
        if let Some(ccc) = char_candidates_confidence {
            write_bin(&dir.join("char_candidates_confidence.bin"), ccc);
        }
        if let Some(ws) = word_source {
            write_bin(&dir.join("word_source.bin"), ws);
        }
        if let Some(cs) = char_source {
            write_bin(&dir.join("char_source.bin"), cs);
        }
        dir
    }

    /// Builds a data dir with word.bin/char.bin plus a separable.bin sidecar
    /// (no other optional sidecars) — for testing the 離合詞 override pass.
    fn make_data_dir_with_separable(
        word: &[(&str, &str)],
        chars: &[(&str, &str)],
        separable: &[(&str, &str)],
    ) -> PathBuf {
        let dir = make_data_dir(word, chars, None, None);
        write_bin(&dir.join("separable.bin"), separable);
        dir
    }

    // ── separable compounds (離合詞) ─────────────────────────────────────────

    #[test]
    fn test_convert_resolves_separable_compound_across_aspect_marker() {
        let dir = make_data_dir_with_separable(
            &[("瞓覺", "fan3 gaau3")],
            &[
                ("覺", "gok3"),
                ("瞓", "fan3"),
                ("緊", "gan2"),
                ("佢", "keoi5"),
            ],
            &[("瞓覺", "fan3 gaau3")],
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert("佢瞓緊覺"), "keoi5 fan3 gan2 gaau3");
    }

    #[test]
    fn test_convert_detailed_reports_separable_compound_source() {
        let dir = make_data_dir_with_separable(
            &[("瞓覺", "fan3 gaau3")],
            &[
                ("覺", "gok3"),
                ("瞓", "fan3"),
                ("緊", "gan2"),
                ("佢", "keoi5"),
            ],
            &[("瞓覺", "fan3 gaau3")],
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_detailed("佢瞓緊覺");
        assert_eq!(
            result,
            vec![
                (
                    "佢".to_string(),
                    "keoi5".to_string(),
                    "yue".to_string(),
                    "certain".to_string(),
                    "unknown".to_string(),
                ),
                (
                    "瞓".to_string(),
                    "fan3".to_string(),
                    "yue".to_string(),
                    "certain".to_string(),
                    "separable_compound".to_string(),
                ),
                (
                    "緊".to_string(),
                    "gan2".to_string(),
                    "yue".to_string(),
                    "certain".to_string(),
                    "unknown".to_string(),
                ),
                (
                    "覺".to_string(),
                    "gaau3".to_string(),
                    "yue".to_string(),
                    "certain".to_string(),
                    "separable_compound".to_string(),
                ),
            ]
        );
    }

    #[test]
    fn test_convert_without_separable_bin_unaffected() {
        // No separable.bin at all — old data dirs keep working, and the
        // override pass simply never fires (pre-fix behavior unchanged).
        let dir = make_data_dir(
            &[("瞓覺", "fan3 gaau3")],
            &[
                ("覺", "gok3"),
                ("瞓", "fan3"),
                ("緊", "gan2"),
                ("佢", "keoi5"),
            ],
            None,
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert("佢瞓緊覺"), "keoi5 fan3 gan2 gok3");
    }

    // ── convert_candidates ───────────────────────────────────────────────────

    #[test]
    fn test_convert_candidates_reports_word_level_ambiguity_with_confidence_and_source() {
        let dir = make_data_dir_full(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "ranked")]),
            None,
            Some(&[("正經", "tojyutping")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("正經");
        assert_eq!(
            result,
            vec![(
                "正經".to_string(),
                vec!["zing3 ging1".to_string(), "zing1 ging1".to_string()],
                "yue".to_string(),
                "ranked".to_string(),
                "tojyutping".to_string(),
            )]
        );
    }

    #[test]
    fn test_convert_candidates_missing_sidecars_default_tied_unknown() {
        // No sidecars at all — Pipeline must still construct and
        // convert_candidates() must fall back to a single reading per token.
        let dir = make_data_dir(&[("香港", "hoeng1 gong2")], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("香港");
        assert_eq!(
            result,
            vec![(
                "香港".to_string(),
                vec!["hoeng1 gong2".to_string()],
                "yue".to_string(),
                "certain".to_string(),
                "unknown".to_string(),
            )]
        );
    }

    #[test]
    fn test_convert_candidates_ambiguous_missing_confidence_and_source_default() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("正經");
        assert_eq!(result[0].3, "tied");
        assert_eq!(result[0].4, "unknown");
    }

    #[test]
    fn test_convert_candidates_user_dict_override_collapses_ambiguity_source_user_dict() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir_opts_with_user_dict(
            &dir,
            true,
            HashMap::from([("正經".to_string(), "zing1 ging1".to_string())]),
        )
        .unwrap();
        let result = p.convert_candidates("正經");
        assert_eq!(
            result,
            vec![(
                "正經".to_string(),
                vec!["zing1 ging1".to_string()],
                "yue".to_string(),
                "certain".to_string(),
                "user_dict".to_string(),
            )]
        );
    }

    #[test]
    fn test_convert_candidates_english_and_punct_passthrough_source() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("hi!");
        assert_eq!(
            result,
            vec![
                (
                    "hi".to_string(),
                    vec!["hi".to_string()],
                    "en".to_string(),
                    "certain".to_string(),
                    "passthrough".to_string(),
                ),
                (
                    "!".to_string(),
                    vec!["!".to_string()],
                    "punct".to_string(),
                    "certain".to_string(),
                    "passthrough".to_string(),
                ),
            ]
        );
    }

    #[test]
    fn test_convert_candidates_empty_text() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_candidates(""), vec![]);
    }

    #[test]
    fn test_convert_candidates_batch_matches_per_text_calls() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1"), ("香港", "hoeng1 gong2")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let texts = vec!["正經".to_string(), "香港".to_string(), "hi!".to_string()];
        let batch_result = p.convert_candidates_batch(&texts);
        let per_text_result: Vec<_> = texts.iter().map(|t| p.convert_candidates(t)).collect();
        assert_eq!(batch_result, per_text_result);
        assert_eq!(batch_result.len(), 3);
    }

    #[test]
    fn test_convert_candidates_batch_empty_input() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_candidates_batch(&[]), Vec::<Vec<_>>::new());
    }

    // ── convert_detailed ─────────────────────────────────────────────────────

    #[test]
    fn test_convert_detailed_reports_rank0_confidence_and_source() {
        let dir = make_data_dir_full(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "tied")]),
            None,
            Some(&[("正經", "tojyutping_tiebreak")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_detailed("正經");
        assert_eq!(
            result,
            vec![(
                "正經".to_string(),
                "zing3 ging1".to_string(),
                "yue".to_string(),
                "tied".to_string(),
                "tojyutping_tiebreak".to_string(),
            )]
        );
    }

    #[test]
    fn test_convert_detailed_no_ambiguity_reports_source() {
        let dir = make_data_dir_full(
            &[("香港", "hoeng1 gong2")],
            &[],
            None,
            None,
            None,
            None,
            Some(&[("香港", "rime")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_detailed("香港");
        assert_eq!(
            result,
            vec![(
                "香港".to_string(),
                "hoeng1 gong2".to_string(),
                "yue".to_string(),
                "certain".to_string(),
                "rime".to_string(),
            )]
        );
    }

    #[test]
    fn test_convert_detailed_empty_text() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_detailed(""), vec![]);
    }

    #[test]
    fn test_convert_detailed_english_and_punct() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_detailed("hi!");
        assert_eq!(
            result,
            vec![
                (
                    "hi".to_string(),
                    "hi".to_string(),
                    "en".to_string(),
                    "certain".to_string(),
                    "passthrough".to_string(),
                ),
                (
                    "!".to_string(),
                    "!".to_string(),
                    "punct".to_string(),
                    "certain".to_string(),
                    "passthrough".to_string(),
                ),
            ]
        );
    }

    #[test]
    fn test_convert_detailed_rank0_matches_convert() {
        let dir = make_data_dir_full(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "ranked")]),
            None,
            Some(&[("正經", "tojyutping")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let detailed = p.convert_detailed("正經");
        assert_eq!(detailed[0].1, p.convert("正經"));
    }

    #[test]
    fn test_convert_detailed_batch_matches_per_text_calls() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1"), ("香港", "hoeng1 gong2")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let texts = vec!["正經".to_string(), "香港".to_string(), "hi!".to_string()];
        let batch_result = p.convert_detailed_batch(&texts);
        let per_text_result: Vec<_> = texts.iter().map(|t| p.convert_detailed(t)).collect();
        assert_eq!(batch_result, per_text_result);
        assert_eq!(batch_result.len(), 3);
    }

    #[test]
    fn test_convert_detailed_batch_empty_input() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_detailed_batch(&[]), Vec::<Vec<_>>::new());
    }
}
