use rayon::prelude::*;
use std::path::PathBuf;
use crate::{normalizer, segment, g2p};
use crate::dict::Dict;

pub struct Pipeline {
    word_dict: Dict,
    char_dict: Dict,
}

fn default_data_dir() -> PathBuf {
    // Look for data/ next to the compiled binary, then fall back to cwd/data/
    let exe = std::env::current_exe().unwrap_or_default();
    let candidate = exe.parent().unwrap_or(std::path::Path::new(".")).join("data");
    if candidate.exists() {
        return candidate;
    }
    PathBuf::from("data")
}

impl Pipeline {
    /// Create a Pipeline loading dict files from the default data/ directory.
    pub fn new() -> Self {
        let data_dir = default_data_dir();
        Self::from_dir(&data_dir)
            .unwrap_or_else(|e| panic!("canto-g2p: failed to load dicts from {:?}: {}", data_dir, e))
    }

    /// Create a Pipeline from a custom directory containing word.bin and char.bin.
    pub fn from_dir(dir: &std::path::Path) -> Result<Self, Box<dyn std::error::Error>> {
        let word_dict = Dict::load(&dir.join("word.bin"))?;
        let char_dict = Dict::load(&dir.join("char.bin"))?;
        Ok(Pipeline { word_dict, char_dict })
    }

    pub fn convert(&self, text: &str) -> String {
        if text.is_empty() {
            return String::new();
        }
        let normalized = normalizer::normalize(text);
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
        let normalized = normalizer::normalize(text);
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
