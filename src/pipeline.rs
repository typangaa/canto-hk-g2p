use crate::dict::Dict;
use crate::{g2p, normalizer, segment};
use rayon::prelude::*;
use std::path::PathBuf;

pub struct Pipeline {
    word_dict: Dict,
    char_dict: Dict,
    pub punc_norm: bool,
}

fn default_data_dir() -> PathBuf {
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
        let word_dict = Dict::load(&dir.join("word.bin"))?;
        let char_dict = Dict::load(&dir.join("char.bin"))?;
        Ok(Pipeline {
            word_dict,
            char_dict,
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
        let tokens = segment::segment_owned(&normalized, &self.word_dict);
        tokens
            .iter()
            .map(|tok| g2p::token_to_jyutping(tok, &self.word_dict, &self.char_dict))
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
        let tokens = segment::segment_owned(&normalized, &self.word_dict);
        tokens
            .into_iter()
            .map(|tok| {
                let jp = g2p::token_to_jyutping(&tok, &self.word_dict, &self.char_dict);
                let lang = classify_lang(&tok).to_owned();
                (tok, jp, lang)
            })
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
