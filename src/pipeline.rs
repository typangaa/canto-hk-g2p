use rayon::prelude::*;
use crate::{normalizer, segment, g2p};

pub struct Pipeline;

impl Pipeline {
    pub fn new() -> Self {
        Pipeline
    }

    pub fn convert(&self, text: &str) -> String {
        let normalized = normalizer::normalize(text);
        let tokens = segment::segment(&normalized);
        tokens
            .iter()
            .map(|tok| g2p::token_to_jyutping(tok))
            .collect::<Vec<_>>()
            .join(" ")
    }

    pub fn convert_batch(&self, texts: &[String]) -> Vec<String> {
        texts.par_iter().map(|t| self.convert(t)).collect()
    }
}
