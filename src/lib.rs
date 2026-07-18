use pyo3::prelude::*;
use pyo3::types::PyList;
use std::collections::HashMap;

pub mod dict;
mod g2p;
mod normalizer;
mod pipeline;
mod segment;
mod user_dict;

pub use pipeline::Pipeline;

/// Cantonese G2P pipeline exposed to Python via PyO3.
#[pyclass]
pub struct PyPipeline {
    inner: pipeline::Pipeline,
}

#[pymethods]
impl PyPipeline {
    /// Create a Pipeline.
    ///
    /// `data_dir` is set by the Python wrapper to the bundled `data/` directory
    /// inside the installed package.  When `None`, Rust falls back to `cwd/data/`
    /// (useful during local development before installing the wheel).
    ///
    /// `user_dict` is a runtime override dictionary (word/char -> jyutping)
    /// layered on top of the shipped dictionaries at the highest priority.
    /// It also participates in segmentation, so a multi-char override is not
    /// silently split apart before lookup. When `None`, behaves exactly as
    /// before this parameter existed.
    #[new]
    #[pyo3(signature = (punc_norm=true, data_dir=None, user_dict=None))]
    pub fn new(
        punc_norm: bool,
        data_dir: Option<&str>,
        user_dict: Option<HashMap<String, String>>,
    ) -> PyResult<Self> {
        let user_dict = user_dict.unwrap_or_default();
        let dir = data_dir
            .map(std::path::PathBuf::from)
            .unwrap_or_else(pipeline::default_data_dir);
        let inner = pipeline::Pipeline::from_dir_opts_with_user_dict(&dir, punc_norm, user_dict)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok(PyPipeline { inner })
    }

    /// Convert a single string to Jyutping-annotated output.
    pub fn convert(&self, text: &str) -> String {
        self.inner.convert(text)
    }

    /// Convert a list of strings in parallel (Rayon).
    pub fn convert_batch(&self, texts: &Bound<'_, PyList>) -> PyResult<Vec<String>> {
        let inputs: Vec<String> = texts
            .iter()
            .map(|item| item.extract::<String>())
            .collect::<PyResult<_>>()?;
        Ok(self.inner.convert_batch(&inputs))
    }

    /// Convert text to a list of (token, jyutping, lang) triples.
    /// lang is "yue" (Cantonese CJK), "en" (Latin/English), or "punct" (punctuation/symbol).
    pub fn convert_detailed(&self, text: &str) -> Vec<(String, String, String)> {
        self.inner.convert_detailed(text)
    }

    /// Convert text to a list of (token, candidate_readings, lang) triples.
    /// candidate_readings is rank-ordered (most-likely first); it has more
    /// than one entry only where the bundled data has 2+ known readings for
    /// that token (or, for OOV single chars, that character). Everything
    /// else reports a single-item list.
    pub fn convert_candidates(&self, text: &str) -> Vec<(String, Vec<String>, String)> {
        self.inner.convert_candidates(text)
    }

    /// Create a Pipeline loading dict files from an explicit directory path.
    #[staticmethod]
    #[pyo3(signature = (dir, punc_norm=true))]
    pub fn from_dir(dir: &str, punc_norm: bool) -> PyResult<Self> {
        pipeline::Pipeline::from_dir_opts(std::path::Path::new(dir), punc_norm)
            .map(|inner| PyPipeline { inner })
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }
}

#[pymodule]
fn _canto_hk_g2p(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyPipeline>()?;
    Ok(())
}
