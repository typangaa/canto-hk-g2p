use crate::dict::Dict;
use crate::user_dict::UserDict;
use crate::{g2p, normalizer, segment};
use rayon::prelude::*;
use std::collections::HashMap;
use std::path::PathBuf;

pub struct Pipeline {
    word_dict: Dict,
    char_dict: Dict,
    user_dict: UserDict,
    /// Sparse rank-ordered candidate readings (Phase 7b-2), only present for
    /// keys with 2+ known readings. `None` if the sidecar `.bin` file is
    /// missing from the data directory — older/custom data dirs still work,
    /// `convert_candidates()` just reports no known ambiguity anywhere.
    word_candidates: Option<Dict>,
    char_candidates: Option<Dict>,
    /// Categorical confidence tag per candidates key ("ranked" | "tied"),
    /// Phase 7b-3 (issue #12). `None` if the sidecar `.bin` is missing —
    /// `convert_candidates_scored()` then defaults every ambiguous token to
    /// `"tied"` (the conservative assumption: no real preference signal).
    word_candidates_confidence: Option<Dict>,
    char_candidates_confidence: Option<Dict>,
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
        Ok(Pipeline {
            word_dict,
            char_dict,
            user_dict: UserDict::new(user_dict),
            word_candidates,
            char_candidates,
            word_candidates_confidence,
            char_candidates_confidence,
            punc_norm,
        })
    }

    pub fn convert(&self, text: &str) -> String {
        if text.is_empty() {
            return String::new();
        }
        let pre = if self.punc_norm {
            normalizer::punc_norm(text)
        } else {
            text.to_owned()
        };
        let normalized = normalizer::normalize(&pre);
        let tokens = segment::segment_owned(&normalized, &self.word_dict, &self.user_dict);
        tokens
            .iter()
            .map(|tok| {
                g2p::token_to_jyutping(tok, &self.word_dict, &self.char_dict, &self.user_dict)
            })
            .collect::<Vec<_>>()
            .join(" ")
    }

    pub fn convert_batch(&self, texts: &[String]) -> Vec<String> {
        texts.par_iter().map(|t| self.convert(t)).collect()
    }

    /// Convert text to structured (token, jyutping, lang) triples.
    /// lang: "yue" = Cantonese CJK, "en" = Latin/English, "punct" = punctuation/symbol.
    pub fn convert_detailed(&self, text: &str) -> Vec<(String, String, String)> {
        if text.is_empty() {
            return vec![];
        }
        let pre = if self.punc_norm {
            normalizer::punc_norm(text)
        } else {
            text.to_owned()
        };
        let normalized = normalizer::normalize(&pre);
        let tokens = segment::segment_owned(&normalized, &self.word_dict, &self.user_dict);
        tokens
            .into_iter()
            .map(|tok| {
                let jp =
                    g2p::token_to_jyutping(&tok, &self.word_dict, &self.char_dict, &self.user_dict);
                let lang = classify_lang(&tok).to_owned();
                (tok, jp, lang)
            })
            .collect()
    }

    /// Convert text to a list of (token, candidate_readings, lang) triples.
    /// `candidate_readings` is rank-ordered (most-likely first); it has more
    /// than one entry only when the token (or, for OOV single chars, the
    /// character) has 2+ known readings in the bundled Candidates API data.
    /// Everything else — unambiguous words, English, punctuation, and OOV
    /// multi-char fallback tokens — reports a single-item list, exactly the
    /// reading `convert_detailed()` would produce.
    pub fn convert_candidates(&self, text: &str) -> Vec<(String, Vec<String>, String)> {
        if text.is_empty() {
            return vec![];
        }
        let pre = if self.punc_norm {
            normalizer::punc_norm(text)
        } else {
            text.to_owned()
        };
        let normalized = normalizer::normalize(&pre);
        let tokens = segment::segment_owned(&normalized, &self.word_dict, &self.user_dict);
        tokens
            .into_iter()
            .map(|tok| {
                let candidates = g2p::token_to_jyutping_candidates(
                    &tok,
                    &self.word_dict,
                    &self.char_dict,
                    &self.user_dict,
                    self.word_candidates.as_ref(),
                    self.char_candidates.as_ref(),
                );
                let lang = classify_lang(&tok).to_owned();
                (tok, candidates, lang)
            })
            .collect()
    }

    /// Rayon-parallel batch sibling of `convert_candidates()` — same
    /// per-text output shape, one `Vec` per input text.
    pub fn convert_candidates_batch(
        &self,
        texts: &[String],
    ) -> Vec<Vec<(String, Vec<String>, String)>> {
        texts
            .par_iter()
            .map(|t| self.convert_candidates(t))
            .collect()
    }

    /// Convert text to a list of (token, candidate_readings, lang, confidence)
    /// tuples (Phase 7b-3, issue #12). Same token/candidate/lang semantics as
    /// `convert_candidates()`, plus a categorical confidence tag per token:
    /// `"certain"` (no ambiguity), `"ranked"` (ToJyutping's own context-aware
    /// ranking), or `"tied"` (rime-cantonese arbitrary tie-break — no real
    /// preference signal; also the default when the confidence sidecar has
    /// no entry for an ambiguous token).
    pub fn convert_candidates_scored(
        &self,
        text: &str,
    ) -> Vec<(String, Vec<String>, String, String)> {
        if text.is_empty() {
            return vec![];
        }
        let pre = if self.punc_norm {
            normalizer::punc_norm(text)
        } else {
            text.to_owned()
        };
        let normalized = normalizer::normalize(&pre);
        let tokens = segment::segment_owned(&normalized, &self.word_dict, &self.user_dict);
        tokens
            .into_iter()
            .map(|tok| {
                let (candidates, confidence) = g2p::token_to_jyutping_candidates_scored(
                    &tok,
                    &self.word_dict,
                    &self.char_dict,
                    &self.user_dict,
                    self.word_candidates.as_ref(),
                    self.char_candidates.as_ref(),
                    self.word_candidates_confidence.as_ref(),
                    self.char_candidates_confidence.as_ref(),
                );
                let lang = classify_lang(&tok).to_owned();
                (tok, candidates, lang, confidence)
            })
            .collect()
    }

    /// Rayon-parallel batch sibling of `convert_candidates_scored()` — same
    /// per-text output shape, one `Vec` per input text.
    #[allow(clippy::type_complexity)]
    pub fn convert_candidates_scored_batch(
        &self,
        texts: &[String],
    ) -> Vec<Vec<(String, Vec<String>, String, String)>> {
        texts
            .par_iter()
            .map(|t| self.convert_candidates_scored(t))
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

    /// Build a temp data dir with word.bin/char.bin, optionally with the
    /// candidates sidecars. Returns the dir (kept alive via the returned
    /// PathBuf's parent staying on disk for the test's duration — cleaned up
    /// by the OS temp dir, matching the pattern used in other test modules).
    fn make_data_dir(
        word: &[(&str, &str)],
        chars: &[(&str, &str)],
        word_candidates: Option<&[(&str, &str)]>,
        char_candidates: Option<&[(&str, &str)]>,
    ) -> PathBuf {
        make_data_dir_scored(word, chars, word_candidates, char_candidates, None, None)
    }

    /// Like `make_data_dir()`, but also optionally writes the confidence
    /// sidecars (Phase 7b-3, issue #12).
    #[allow(clippy::too_many_arguments)]
    fn make_data_dir_scored(
        word: &[(&str, &str)],
        chars: &[(&str, &str)],
        word_candidates: Option<&[(&str, &str)]>,
        char_candidates: Option<&[(&str, &str)]>,
        word_candidates_confidence: Option<&[(&str, &str)]>,
        char_candidates_confidence: Option<&[(&str, &str)]>,
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
        dir
    }

    #[test]
    fn test_convert_candidates_reports_word_level_ambiguity() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("正經");
        assert_eq!(
            result,
            vec![(
                "正經".to_string(),
                vec!["zing3 ging1".to_string(), "zing1 ging1".to_string()],
                "yue".to_string()
            )]
        );
    }

    #[test]
    fn test_convert_candidates_missing_sidecars_behave_like_no_ambiguity() {
        // No candidates sidecars at all — Pipeline must still construct and
        // convert_candidates() must fall back to a single reading per token.
        let dir = make_data_dir(&[("香港", "hoeng1 gong2")], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("香港");
        assert_eq!(
            result,
            vec![(
                "香港".to_string(),
                vec!["hoeng1 gong2".to_string()],
                "yue".to_string()
            )]
        );
    }

    #[test]
    fn test_convert_candidates_user_dict_override_collapses_ambiguity() {
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
                "yue".to_string()
            )]
        );
    }

    #[test]
    fn test_convert_candidates_english_and_punct_single_item() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates("hi!");
        assert_eq!(
            result,
            vec![
                ("hi".to_string(), vec!["hi".to_string()], "en".to_string()),
                ("!".to_string(), vec!["!".to_string()], "punct".to_string()),
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

    // ── convert_candidates_scored (Phase 7b-3, issue #12) ────────────────────

    #[test]
    fn test_convert_candidates_scored_ranked() {
        let dir = make_data_dir_scored(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "ranked")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates_scored("正經");
        assert_eq!(
            result,
            vec![(
                "正經".to_string(),
                vec!["zing3 ging1".to_string(), "zing1 ging1".to_string()],
                "yue".to_string(),
                "ranked".to_string()
            )]
        );
    }

    #[test]
    fn test_convert_candidates_scored_tied() {
        let dir = make_data_dir_scored(
            &[("處理", "cyu2 lei5")],
            &[],
            Some(&[("處理", "cyu2 lei5|cyu5 lei5")]),
            None,
            Some(&[("處理", "tied")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates_scored("處理");
        assert_eq!(result[0].3, "tied");
    }

    #[test]
    fn test_convert_candidates_scored_missing_confidence_sidecar_defaults_tied() {
        let dir = make_data_dir(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates_scored("正經");
        assert_eq!(result[0].3, "tied");
    }

    #[test]
    fn test_convert_candidates_scored_no_ambiguity_is_certain() {
        let dir = make_data_dir(&[("香港", "hoeng1 gong2")], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates_scored("香港");
        assert_eq!(
            result,
            vec![(
                "香港".to_string(),
                vec!["hoeng1 gong2".to_string()],
                "yue".to_string(),
                "certain".to_string()
            )]
        );
    }

    #[test]
    fn test_convert_candidates_scored_user_dict_override_is_certain() {
        let dir = make_data_dir_scored(
            &[("正經", "zing3 ging1")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "ranked")]),
            None,
        );
        let p = Pipeline::from_dir_opts_with_user_dict(
            &dir,
            true,
            HashMap::from([("正經".to_string(), "zing1 ging1".to_string())]),
        )
        .unwrap();
        let result = p.convert_candidates_scored("正經");
        assert_eq!(result[0].3, "certain");
    }

    #[test]
    fn test_convert_candidates_scored_english_and_punct_certain() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        let result = p.convert_candidates_scored("hi!");
        assert_eq!(
            result,
            vec![
                (
                    "hi".to_string(),
                    vec!["hi".to_string()],
                    "en".to_string(),
                    "certain".to_string()
                ),
                (
                    "!".to_string(),
                    vec!["!".to_string()],
                    "punct".to_string(),
                    "certain".to_string()
                ),
            ]
        );
    }

    #[test]
    fn test_convert_candidates_scored_empty_text() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_candidates_scored(""), vec![]);
    }

    #[test]
    fn test_convert_candidates_scored_batch_matches_per_text_calls() {
        let dir = make_data_dir_scored(
            &[("正經", "zing3 ging1"), ("香港", "hoeng1 gong2")],
            &[],
            Some(&[("正經", "zing3 ging1|zing1 ging1")]),
            None,
            Some(&[("正經", "ranked")]),
            None,
        );
        let p = Pipeline::from_dir(&dir).unwrap();
        let texts = vec!["正經".to_string(), "香港".to_string(), "hi!".to_string()];
        let batch_result = p.convert_candidates_scored_batch(&texts);
        let per_text_result: Vec<_> = texts
            .iter()
            .map(|t| p.convert_candidates_scored(t))
            .collect();
        assert_eq!(batch_result, per_text_result);
        assert_eq!(batch_result.len(), 3);
    }

    #[test]
    fn test_convert_candidates_scored_batch_empty_input() {
        let dir = make_data_dir(&[], &[], None, None);
        let p = Pipeline::from_dir(&dir).unwrap();
        assert_eq!(p.convert_candidates_scored_batch(&[]), Vec::<Vec<_>>::new());
    }
}
