"""Fast better_profanity-compatible filter, implemented in Rust."""

from __future__ import annotations

import os
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

from better_profanity_fast._native import Engine

__all__ = ["Profanity", "profanity", "WORDLIST_ENV"]

# Wordlist is Python package data, not compiled into the native library.
# Replace this file, or set the env var, without rebuilding the .so/.dylib/.pyd.
WORDLIST_ENV = "BETTER_PROFANITY_WORDLIST"


def _packaged_wordlist_file():
    return files("better_profanity_fast").joinpath("wordlist.txt")


def _read_wordlist_file(path):
    words = []
    with open(path, encoding="utf-8") as handle:
        for row in handle:
            row = row.strip()
            if row:
                words.append(row)
    return words


def _default_words():
    override = os.environ.get(WORDLIST_ENV)
    if override:
        if not os.path.isfile(override):
            raise FileNotFoundError(override)
        return _read_wordlist_file(override)
    return [
        line.strip()
        for line in _packaged_wordlist_file().read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _as_str_list(words):
    return [word for word in words if isinstance(word, str)]


class Profanity:
    """better_profanity-style API over the Rust matcher."""

    def __init__(self, words=None):
        if (
            words is not None
            and not isinstance(words, (str, Path))
            and not isinstance(words, Iterable)
        ):
            raise TypeError("words must be of type str, list, or None")
        self._engine = Engine()
        if words is None:
            self.load_censor_words()
        elif isinstance(words, (str, Path)):
            self.load_censor_words_from_file(words)
        else:
            self._engine.load(_as_str_list(words), [])

    def load_censor_words(self, custom_words=None, whitelist_words=None):
        if whitelist_words is not None and not isinstance(
            whitelist_words, (list, set, tuple)
        ):
            raise TypeError(
                "The 'whitelist_words' keyword argument only accepts list, tuple or set."
            )
        whitelist = _as_str_list(whitelist_words or [])
        if custom_words is None:
            self._engine.load(_default_words(), whitelist)
            return
        if isinstance(custom_words, (str, Path)):
            self.load_censor_words_from_file(
                custom_words, whitelist_words=whitelist_words
            )
            return
        if not isinstance(custom_words, Iterable):
            raise TypeError("words must be of type str, list, or None")
        self._engine.load(_as_str_list(custom_words), whitelist)

    def load_censor_words_from_file(self, filename, whitelist_words=None, **kwargs):
        if not os.path.isfile(filename):
            raise FileNotFoundError(str(filename))
        words = _read_wordlist_file(filename)
        whitelist = whitelist_words if whitelist_words is not None else kwargs.get(
            "whitelist_words"
        )
        self.load_censor_words(words, whitelist_words=whitelist)

    def add_censor_words(self, custom_words):
        if not isinstance(custom_words, (list, tuple, set)):
            raise TypeError(
                "Function 'add_censor_words' only accepts list, tuple or set."
            )
        for word in custom_words:
            if isinstance(word, str):
                self._engine.add_word(word)

    def contains_word(self, word):
        if not isinstance(word, str):
            word = str(word)
        return bool(self._engine.contains_word(word))

    def contains_profanity(self, text):
        if not isinstance(text, str):
            text = str(text)
        return bool(self._engine.contains_profanity(text))

    def censor(self, text, censor_char="*"):
        if not isinstance(text, str):
            text = str(text)
        if not isinstance(censor_char, str):
            censor_char = str(censor_char)
        return self._engine.censor(text, censor_char)


# Empty until tests/callers load a list, matching better_profanity's singleton.
profanity = Profanity([])
