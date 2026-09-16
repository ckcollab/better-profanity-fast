# better-profanity-fast

Fast [better_profanity](https://pypi.org/project/better-profanity/)-compatible
profanity filter. Matching runs in Rust; Python is only the public API.

There is **no pure-Python fallback**. Install a wheel for your OS/CPU, or build
from the sdist with a Rust toolchain.

```python
from better_profanity_fast import Profanity

filt = Profanity()  # default wordlist; construct once per process
filt.contains_profanity("he is a m0th3rf*cker")  # True
filt.censor("Dude, I hate shit.")  # 'Dude, I hate ****.'
```

In Django, create one `Profanity()` at import / AppConfig ready time. Do not
build a new filter on every request.

## Benchmark vs better_profanity 0.7

Same process, same 916-word list (`wordlist.txt`), CPython 3.14 on macOS arm64.
Median of 3+ rounds. Speedup is 0.7 time / this package (higher means faster).

0.7 walks a `VaryingString` list per token, so a ~14k-character paragraph takes
**~2.8 seconds**. This package hashes leet variants and scans in Rust.

`contains_profanity` on dirty text early-exits here; 0.7 still scans. Censor
always walks the full string on both sides, so the long-censor rows (~3700x)
are the fairest like-for-like comparison.

Construct the filter once. Init is slower than 0.7 because we pre-expand leet
hashes (~500k) at load time.

| Operation | Workload | better_profanity 0.7 | better-profanity-fast | Speedup |
|---|---|---:|---:|---:|
| init | 916-word list | 2.1 ms | 16.5 ms | 0.12x |
| contains_profanity | short clean (75 chars) | 13.6 ms | 5.5 µs | 2500x |
| contains_profanity | short profane (57 chars) | 7.1 ms | 2.0 µs | 3500x |
| contains_profanity | short leet (68 chars) | 12.6 ms | 1.4 µs | 9200x |
| contains_profanity | long clean (13884 chars) | 2.77 s | 746 µs | 3700x |
| contains_profanity | long profane (13949 chars) | 2.75 s | 30 µs | 92000x |
| contains_profanity | long leet (13927 chars) | 2.77 s | 51 µs | 54000x |
| censor | short clean (75 chars) | 13.5 ms | 5.6 µs | 2400x |
| censor | short profane (57 chars) | 7.1 ms | 3.7 µs | 1900x |
| censor | short leet (68 chars) | 12.5 ms | 4.9 µs | 2600x |
| censor | long clean (13884 chars) | 2.85 s | 768 µs | 3700x |
| censor | long profane (13949 chars) | 2.81 s | 764 µs | 3700x |
| censor | long leet (13927 chars) | 2.80 s | 772 µs | 3600x |

Matching is not identical to 0.7: this package also catches stretched spellings
(`peenis`) and long infixes (`ThisRetard`). The table still uses the same
inputs on both libraries.

## Install

```bash
pip install better-profanity-fast
```

Requires CPython 3.9+. Wheels are **abi3**: one Linux/macOS/Windows wheel
covers every CPython version from 3.9 through 3.14. Alpine needs the
`musllinux` wheel (also published).

The default wordlist is `wordlist.txt` in the Python package, not inside the
native library. Swap that file, or set `BETTER_PROFANITY_WORDLIST` to another
path, then construct a new `Profanity()` — no Rust rebuild.

```bash
export BETTER_PROFANITY_WORDLIST=/etc/my-app/wordlist.txt
```

A dictionary letter may consume at most 8 identical input characters
(`peenis` still matches; 9+ repeats of the same letter do not).

Digit-only tokens (`1011`, years, ports, order IDs) are never treated as
leetspeak. Phrases that happen to contain digits (`2 girls 1 cup`) still match.

## Local development

```bash
pip install maturin
maturin develop --release
cargo test --release --lib
python -m unittest discover -s tests -v
```

## License

MIT. Copyright (c) 2026 Eric Carmichael. The default wordlist is adapted from
better_profanity (MIT).
