mod engine;

use pyo3::prelude::*;

use engine::ProfanityTrie;

/// Native matcher. The public Python API lives in `better_profanity_fast.Profanity`.
#[pyclass(module = "better_profanity_fast._native")]
pub struct Engine {
    inner: ProfanityTrie,
}

#[pymethods]
impl Engine {
    #[new]
    fn new() -> Self {
        Self {
            inner: ProfanityTrie::from_words(std::iter::empty::<String>()),
        }
    }

    fn load(&mut self, words: Vec<String>, whitelist: Vec<String>) {
        self.inner.reload(words, whitelist);
    }

    fn add_word(&mut self, word: &str) {
        self.inner.add_censor_word(word);
    }

    fn contains_word(&self, word: &str) -> bool {
        self.inner.contains_word(word)
    }

    fn contains_profanity(&self, text: &str) -> bool {
        self.inner.contains_profanity(text)
    }

    #[pyo3(signature = (text, censor_char = "*"))]
    fn censor(&self, text: &str, censor_char: &str) -> String {
        let ch = censor_char.chars().next().unwrap_or('*');
        self.inner.censor(text, ch)
    }
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Engine>()?;
    Ok(())
}
