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
}
