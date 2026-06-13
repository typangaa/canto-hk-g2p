use pyo3::prelude::*;
use pyo3::types::PyList;

mod normalizer;
mod segment;
mod g2p;
mod pipeline;
pub mod dict;

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
    #[new]
    #[pyo3(signature = (punc_norm=true, data_dir=None))]
    pub fn new(punc_norm: bool, data_dir: Option<&str>) -> PyResult<Self> {
        let inner = match data_dir {
            Some(dir) => pipeline::Pipeline::from_dir_opts(
                std::path::Path::new(dir), punc_norm)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?,
            None => pipeline::Pipeline::new_with_opts(punc_norm),
        };
        Ok(PyPipeline { inner })
    }

    /// Convert a single string to Jyutping-annotated output.
    pub fn convert(&self, text: &str) -> String {
        self.inner.convert(text)
    }

    /// Convert a list of strings in parallel (Rayon).
    pub fn convert_batch(&self, py: Python<'_>, texts: &Bound<'_, PyList>) -> PyResult<Vec<String>> {
        let inputs: Vec<String> = texts
            .iter()
            .map(|item| item.extract::<String>())
            .collect::<PyResult<_>>()?;
        let results = py.allow_threads(|| self.inner.convert_batch(&inputs));
        Ok(results)
    }

    /// Convert text to a list of (token, jyutping, lang) triples.
    /// lang is "yue" (Cantonese CJK), "en" (Latin/English), or "punct" (punctuation/symbol).
    pub fn convert_detailed(&self, text: &str) -> Vec<(String, String, String)> {
        self.inner.convert_detailed(text)
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
