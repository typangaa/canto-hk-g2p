use pyo3::prelude::*;
use pyo3::types::PyList;

mod normalizer;
mod segment;
mod g2p;
mod pipeline;

pub use pipeline::Pipeline;

/// Cantonese G2P pipeline exposed to Python via PyO3.
#[pyclass]
pub struct PyPipeline {
    inner: pipeline::Pipeline,
}

#[pymethods]
impl PyPipeline {
    #[new]
    pub fn new() -> PyResult<Self> {
        Ok(PyPipeline {
            inner: pipeline::Pipeline::new(),
        })
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
}

#[pymodule]
fn _canto_g2p(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyPipeline>()?;
    Ok(())
}
