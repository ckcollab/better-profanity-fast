//! Fast leetspeak-preserving profanity matcher.
//!
//! Exact 0.7 leet hits are FNV-1a hashes (no stored variant strings).
//! The trie still handles stretch, infix, and space-joined prefixes.

use rustc_hash::{FxHashMap, FxHashSet};
use std::sync::OnceLock;
use unicode_normalization::UnicodeNormalization;

const MIN_STRETCH_WORD_LEN: usize = 4;
const MIN_INFIX_WORD_LEN: usize = 6;
/// One dictionary letter may consume at most this many identical input chars.
/// Caps stretch DFS (`for consume in 1..=run`) so a 10k-char run is not a bomb.
const MAX_STRETCH_RUN: usize = 8;
const LEET_SYMBOLS: &[char] = &['@', '$', '*', '"', '\''];
const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x100_0000_01b3;

fn nfc(text: &str) -> String {
    text.nfc().collect()
}

fn normalize_word(word: &str) -> String {
    if word.is_ascii() {
        word.to_ascii_lowercase()
    } else {
        nfc(word).to_lowercase()
    }
}

#[inline]
fn is_mn(ch: char) -> bool {
    unicode_normalization::char::canonical_combining_class(ch) != 0
}

#[inline]
fn is_word_char(ch: char) -> bool {
    ch.is_alphabetic() || ch.is_ascii_digit() || matches!(ch, '@' | '$' | '*' | '"' | '\'') || is_mn(ch)
}

#[inline]
fn hash_chars(chars: &[char]) -> u64 {
    let mut h = FNV_OFFSET;
    for &c in chars {
        h ^= c as u64;
        h = h.wrapping_mul(FNV_PRIME);
    }
    h ^= chars.len() as u64;
    h.wrapping_mul(FNV_PRIME)
}

fn hash_str(text: &str) -> u64 {
    let mut buf = Vec::with_capacity(text.chars().count());
    buf.extend(text.chars());
    hash_chars(&buf)
}

/// Digit-only tokens are never profanity. `1011`, years, ports, order IDs, etc.
/// stay as numbers — `1`/`0` are not treated as `l`/`o`. Mixed tokens (`h0mo`,
/// `sh1t`) and phrases that contain digits (`2 girls 1 cup`) still match.
#[inline]
fn is_pure_number(chars: &[char]) -> bool {
    !chars.is_empty() && chars.iter().all(|ch| ch.is_ascii_digit())
}

#[inline]
fn has_repeated_run_slice(chars: &[char]) -> bool {
    chars.windows(2).any(|w| w[0] == w[1])
}

fn fold_into(src: &[char], dest: &mut Vec<char>) {
    dest.clear();
    dest.extend(src.iter().copied().filter(|ch| !is_mn(*ch)));
}

fn push_lower(ch: char, buf: &mut Vec<char>) {
    if ch.is_ascii() {
        buf.push(if ch.is_ascii_uppercase() {
            (ch as u8 + 32) as char
        } else {
            ch
        });
    } else {
        buf.extend(ch.to_lowercase());
    }
}

fn variants_of(ch: char) -> &'static [char] {
    match ch {
        'a' => &['a', '@', '*', '4'],
        'i' => &['i', '*', 'l', '1'],
        'o' => &['o', '*', '0', '@'],
        'u' => &['u', '*', 'v'],
        'v' => &['v', '*', 'u'],
        'l' => &['l', '1'],
        'e' => &['e', '*', '3'],
        's' => &['s', '$', '5'],
        't' => &['t', '7'],
        _ => &[],
    }
}

/// Input char -> dictionary letters it can stand for (ASCII leet only).
fn ascii_canons(ch: char) -> &'static [char] {
    match ch {
        'a' => &['a'],
        '@' => &['a', 'o'],
        '*' => &['a', 'i', 'o', 'u', 'v', 'e'],
        '4' => &['a'],
        'i' => &['i'],
        'l' => &['i', 'l'],
        '1' => &['i', 'l'],
        'o' => &['o'],
        '0' => &['o'],
        'u' => &['u', 'v'],
        'v' => &['v', 'u'],
        'e' => &['e'],
        '3' => &['e'],
        's' => &['s'],
        '$' => &['s'],
        '5' => &['s'],
        't' => &['t'],
        '7' => &['t'],
        _ => &[],
    }
}

fn reverse_leet() -> &'static FxHashMap<char, Vec<char>> {
    static MAP: OnceLock<FxHashMap<char, Vec<char>>> = OnceLock::new();
    MAP.get_or_init(|| {
        let mut grouped: FxHashMap<char, FxHashSet<char>> = FxHashMap::default();
        for canon in ['a', 'i', 'o', 'u', 'v', 'l', 'e', 's', 't'] {
            for alt in variants_of(canon) {
                grouped.entry(*alt).or_default().insert(canon);
            }
            grouped.entry(canon).or_default().insert(canon);
        }
        grouped
            .into_iter()
            .map(|(k, v)| (k, v.into_iter().collect()))
            .collect()
    })
}

fn expand_hashes(set: &mut FxHashSet<u64>, word: &str) {
    let chars: Vec<char> = word.chars().collect();
    if chars.is_empty() {
        return;
    }
    let mut estimate = 1usize;
    for &ch in &chars {
        let mapped = variants_of(ch);
        estimate = estimate.saturating_mul(if mapped.is_empty() { 1 } else { mapped.len() });
    }
    set.reserve(estimate);
    let mut buf = Vec::with_capacity(chars.len());
    expand_rec(set, &chars, 0, &mut buf);
}

fn expand_rec(set: &mut FxHashSet<u64>, chars: &[char], pos: usize, buf: &mut Vec<char>) {
    if pos == chars.len() {
        set.insert(hash_chars(buf));
        return;
    }
    let mapped = variants_of(chars[pos]);
    if mapped.is_empty() {
        buf.push(chars[pos]);
        expand_rec(set, chars, pos + 1, buf);
        buf.pop();
        return;
    }
    for &extra in mapped {
        buf.push(extra);
        expand_rec(set, chars, pos + 1, buf);
        buf.pop();
    }
}

struct Node {
    children: FxHashMap<char, Node>,
    is_end: bool,
}

impl Node {
    fn new() -> Self {
        Self {
            children: FxHashMap::default(),
            is_end: false,
        }
    }
}

fn insert_word(root: &mut Node, word: &str) {
    let mut node = root;
    for ch in word.chars() {
        node = node.children.entry(ch).or_insert_with(Node::new);
    }
    node.is_end = true;
}

pub struct ProfanityTrie {
    root: Node,
    phrase_root: Node,
    has_phrases: bool,
    max_join_words: usize,
    whitelist: FxHashSet<String>,
    whitelist_hashes: FxHashSet<u64>,
    expanded: FxHashSet<u64>,
    phrase_expanded: FxHashSet<u64>,
}

impl ProfanityTrie {
    pub fn from_words<I>(words: I) -> Self
    where
        I: IntoIterator<Item = String>,
    {
        Self::from_words_with_whitelist(words, std::iter::empty::<String>())
    }

    pub fn from_words_with_whitelist<I, W>(words: I, whitelist: W) -> Self
    where
        I: IntoIterator<Item = String>,
        W: IntoIterator<Item = String>,
    {
        let whitelist: FxHashSet<String> = whitelist.into_iter().map(|word| normalize_word(&word)).collect();
        let whitelist_hashes = whitelist.iter().map(|word| hash_str(word)).collect();
        let mut filter = Self {
            root: Node::new(),
            phrase_root: Node::new(),
            has_phrases: false,
            max_join_words: 1,
            whitelist,
            whitelist_hashes,
            expanded: FxHashSet::default(),
            phrase_expanded: FxHashSet::default(),
        };
        let mut seen = FxHashSet::default();
        for word in words {
            if seen.insert(word.clone()) {
                filter.add_word(&word);
            }
        }
        filter
    }

    pub fn reload<I, W>(&mut self, words: I, whitelist: W)
    where
        I: IntoIterator<Item = String>,
        W: IntoIterator<Item = String>,
    {
        *self = Self::from_words_with_whitelist(words, whitelist);
    }

    pub fn add_censor_word(&mut self, word: &str) {
        self.add_word(word);
    }

    fn add_word(&mut self, word: &str) {
        let lowered = normalize_word(word);
        let lowered = lowered.trim();
        if lowered.is_empty() || self.whitelist.contains(lowered) {
            return;
        }
        let normalized: String = lowered.chars().filter(|ch| !is_mn(*ch) && ch.is_alphanumeric()).collect();
        if normalized.is_empty() || self.whitelist.contains(&normalized) {
            return;
        }

        insert_word(&mut self.root, &normalized);
        expand_hashes(&mut self.expanded, &normalized);
        self.max_join_words = self.max_join_words.max(normalized.chars().count());

        let compact: String = lowered.chars().filter(|ch| !is_mn(*ch) && !ch.is_whitespace()).collect();
        if compact != normalized {
            expand_hashes(&mut self.expanded, &compact);
        }

        if lowered.contains(' ') {
            insert_word(&mut self.phrase_root, &normalized);
            expand_hashes(&mut self.phrase_expanded, &normalized);
            self.has_phrases = true;
            let tokens = lowered.split_whitespace().count();
            self.max_join_words = self.max_join_words.max(tokens);
            if compact != normalized {
                expand_hashes(&mut self.phrase_expanded, &compact);
            }
        }
    }

    pub fn contains_word(&self, word: &str) -> bool {
        let mut collapsed = Vec::with_capacity(word.len());
        if word.is_ascii() {
            for b in word.bytes() {
                let ch = if b.is_ascii_uppercase() {
                    (b + 32) as char
                } else {
                    b as char
                };
                if ch.is_ascii_alphanumeric() || LEET_SYMBOLS.contains(&ch) {
                    collapsed.push(ch);
                }
            }
        } else {
            for ch in nfc(word).to_lowercase().chars() {
                if is_mn(ch) {
                    continue;
                }
                if ch.is_alphanumeric() || LEET_SYMBOLS.contains(&ch) {
                    collapsed.push(ch);
                }
            }
        }
        self.chars_match(&collapsed)
    }

    pub fn contains_profanity(&self, text: &str) -> bool {
        if text.is_empty() {
            return false;
        }
        !self.find_spans(text, Some(1)).is_empty()
    }

    pub fn censor(&self, text: &str, censor_char: char) -> String {
        if text.is_empty() {
            return text.to_string();
        }
        if text.is_ascii() {
            let spans = self.find_spans(text, None);
            if spans.is_empty() {
                return text.to_string();
            }
            let replacement = censor_char.to_string().repeat(4);
            let mut out = String::with_capacity(text.len());
            let mut cursor = 0usize;
            for (start, end) in spans {
                out.push_str(&text[cursor..start]);
                out.push_str(&replacement);
                cursor = end;
            }
            out.push_str(&text[cursor..]);
            return out;
        }
        let text = nfc(text);
        let spans = self.find_spans(&text, None);
        if spans.is_empty() {
            return text;
        }
        let replacement = censor_char.to_string().repeat(4);
        let mut out = String::new();
        let mut cursor = 0usize;
        let chars: Vec<char> = text.chars().collect();
        for (start, end) in spans {
            out.extend(chars[cursor..start].iter());
            out.push_str(&replacement);
            cursor = end;
        }
        out.extend(chars[cursor..].iter());
        out
    }

    fn chars_match(&self, collapsed: &[char]) -> bool {
        if is_pure_number(collapsed) {
            return false;
        }
        if self.expanded.contains(&hash_chars(collapsed)) {
            return true;
        }
        if !has_repeated_run_slice(collapsed) {
            return false;
        }
        walk_chars(&self.root, collapsed, true, false)
    }

    fn phrase_match(&self, collapsed: &[char]) -> bool {
        if !self.has_phrases {
            return false;
        }
        if self.phrase_expanded.contains(&hash_chars(collapsed)) {
            return true;
        }
        if !has_repeated_run_slice(collapsed) {
            return false;
        }
        walk_chars(&self.phrase_root, collapsed, true, false)
    }

    fn could_be_phrase(&self, collapsed: &[char]) -> bool {
        !is_pure_number(collapsed)
            && self.has_phrases
            && walk_chars(&self.phrase_root, collapsed, false, false)
    }

    fn could_be_word(&self, collapsed: &[char]) -> bool {
        !is_pure_number(collapsed) && walk_chars(&self.root, collapsed, false, false)
    }

    fn is_whitelisted(&self, folded: &[char], raw: &[char]) -> bool {
        if self.whitelist_hashes.is_empty() {
            return false;
        }
        self.whitelist_hashes.contains(&hash_chars(folded)) || self.whitelist_hashes.contains(&hash_chars(raw))
    }

    fn contains_embedded(&self, folded: &[char]) -> bool {
        let n = folded.len();
        if n < MIN_INFIX_WORD_LEN || is_pure_number(folded) {
            return false;
        }
        // Walk the trie from each start. That finds exact leet infixes and
        // stretch in one pass. Hashing every [start, end] substring was O(n²).
        // Never begin an infix match on a digit (IDs embedded in a token).
        for start in 0..=n - MIN_INFIX_WORD_LEN {
            if folded[start].is_ascii_digit() {
                continue;
            }
            if walk_chars(&self.root, &folded[start..], true, true) {
                return true;
            }
        }
        false
    }

    fn find_spans(&self, text: &str, stop_after: Option<usize>) -> Vec<(usize, usize)> {
        let chars: Vec<char> = if text.is_ascii() {
            text.chars().collect()
        } else {
            nfc(text).chars().collect()
        };
        self.find_spans_on_chars(&chars, stop_after)
    }

    fn find_spans_on_chars(&self, chars: &[char], stop_after: Option<usize>) -> Vec<(usize, usize)> {
        let words = iter_word_spans(chars);
        if words.is_empty() {
            return Vec::new();
        }
        let mut used = vec![false; words.len()];
        let mut spans = Vec::new();
        let mut raw = Vec::new();
        let mut folded = Vec::new();
        let mut trial = Vec::new();

        for i in 0..words.len() {
            if used[i] {
                continue;
            }
            let mut best_j = None;
            raw.clear();
            let max_j = words.len().min(i + self.max_join_words);
            for j in i..max_j {
                let (start, end) = words[j];
                if j > i {
                    let prev_end = words[j - 1].1;
                    if chars[prev_end..start].iter().any(|ch| ch.is_whitespace()) {
                        trial.clear();
                        trial.extend(raw.iter().copied().filter(|ch| !is_mn(*ch)));
                        for &ch in &chars[start..end] {
                            if !is_mn(ch) {
                                push_lower(ch, &mut trial);
                            }
                        }
                        if !self.could_be_word(&trial) && !self.could_be_phrase(&trial) {
                            break;
                        }
                    }
                    for &ch in &chars[start..end] {
                        push_lower(ch, &mut raw);
                    }
                } else {
                    raw.clear();
                    for &ch in &chars[start..end] {
                        push_lower(ch, &mut raw);
                    }
                }
                fold_into(&raw, &mut folded);
                if is_pure_number(&folded) {
                    continue;
                }
                if !self.chars_match(&folded) && !self.phrase_match(&folded) {
                    continue;
                }
                if self.is_whitelisted(&folded, &raw) {
                    continue;
                }
                best_j = Some(j);
            }
            if best_j.is_none() {
                raw.clear();
                let (start, end) = words[i];
                for &ch in &chars[start..end] {
                    push_lower(ch, &mut raw);
                }
                fold_into(&raw, &mut folded);
                if self.is_whitelisted(&folded, &raw) {
                    continue;
                }
                if !self.contains_embedded(&folded) {
                    continue;
                }
                best_j = Some(i);
            }
            let j = best_j.unwrap();
            spans.push((words[i].0, words[j].1));
            if let Some(limit) = stop_after {
                if spans.len() >= limit {
                    return spans;
                }
            }
            for k in i..=j {
                used[k] = true;
            }
        }
        spans
    }
}

fn iter_word_spans(chars: &[char]) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if !is_word_char(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        i += 1;
        while i < chars.len() && is_word_char(chars[i]) {
            i += 1;
        }
        out.push((start, i));
    }
    out
}

#[inline]
fn char_matches_canon(ch: char, canon: char) -> bool {
    if ch == canon {
        return true;
    }
    if ch.is_ascii() {
        return ascii_canons(ch).contains(&canon);
    }
    reverse_leet().get(&ch).is_some_and(|canons| canons.contains(&canon))
}

fn matching_run_length(collapsed: &[char], index: usize, canon: char) -> usize {
    if index >= collapsed.len() || !char_matches_canon(collapsed[index], canon) {
        return 0;
    }
    let first = collapsed[index];
    let mut n = 1;
    while n < MAX_STRETCH_RUN && index + n < collapsed.len() && collapsed[index + n] == first {
        n += 1;
    }
    n
}

fn walk_chars(root: &Node, chars: &[char], require_end: bool, infix: bool) -> bool {
    if chars.is_empty() {
        return false;
    }
    let length = chars.len();
    let mut stack = vec![(0usize, root, 0usize, false)];
    let mut canons = Vec::with_capacity(8);
    while let Some((index, node, depth, used_stretch)) = stack.pop() {
        if infix {
            if node.is_end && depth >= MIN_INFIX_WORD_LEN && index > 0 && !is_pure_number(&chars[..index]) {
                return true;
            }
            if index == length {
                continue;
            }
        } else if index == length {
            if require_end && !node.is_end {
                continue;
            }
            if used_stretch && depth < MIN_STRETCH_WORD_LEN {
                continue;
            }
            if is_pure_number(chars) {
                continue;
            }
            return true;
        }

        let ch = chars[index];
        canons.clear();
        if ch.is_ascii() {
            canons.extend_from_slice(ascii_canons(ch));
        } else if let Some(candidates) = reverse_leet().get(&ch) {
            canons.extend_from_slice(candidates);
        }
        if !canons.contains(&ch) {
            canons.push(ch);
        }
        for &canon in &canons {
            if let Some(child) = node.children.get(&canon) {
                let run = matching_run_length(chars, index, canon);
                for consume in 1..=run {
                    stack.push((index + consume, child, depth + 1, used_stretch || consume > 1));
                }
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ProfanityTrie {
        ProfanityTrie::from_words(
            ["fuck", "shit", "hand job", "ass", "penis", "retard"]
                .into_iter()
                .map(|s| s.to_string()))
    }

    #[test]
    fn expanded_set_and_stretch() {
        let trie = sample();
        assert!(trie.contains_word("fuck"));
        assert!(trie.contains_word("f*ck"));
        assert!(trie.contains_word("fvck"));
        assert!(trie.contains_word("peenis"));
        assert!(!trie.contains_word("class"));
        assert!(!trie.contains_word("fck"));
        assert!(trie.contains_word("peeeeeeeenis")); // 8 e's, at the cap
        assert!(!trie.contains_word("peeeeeeeeenis")); // 9 e's
    }

    #[test]
    fn infix_and_censor() {
        let trie = sample();
        assert!(trie.contains_profanity("ThisRetard"));
        assert_eq!(trie.censor("Dude, I hate shit.", '*'), "Dude, I hate ****.");
        assert!(!trie.contains_profanity("hello there"));
        assert!(!trie.contains_profanity("ThisPenis"));
        assert!(!trie.contains_profanity("stardust"));
        assert!(!trie.contains_profanity("public"));
        for number in ["0", "69", "420", "911", "1011", "2026", "8080"] {
            assert!(!trie.contains_word(number), "{number}");
            assert!(!trie.contains_profanity(number), "{number}");
            assert_eq!(trie.censor(number, '*'), number, "{number}");
        }
        let phrases = ProfanityTrie::from_words(["2 girls 1 cup"].into_iter().map(|s| s.to_string()));
        assert!(phrases.contains_profanity("2 girls 1 cup"));
    }

    #[test]
    fn giant_token_infix_is_bounded() {
        let trie = sample();
        let token = "x".repeat(20_000);
        let started = std::time::Instant::now();
        assert!(!trie.contains_profanity(&token));
        assert!(
            started.elapsed().as_millis() < 200,
            "infix scan of a 20k token took {:?}",
            started.elapsed()
        );
    }

    #[test]
    fn joins_handjob_across_spaces() {
        let trie = ProfanityTrie::from_words(
            ["handjob", "whore"].into_iter().map(|s| s.to_string()));
        assert_eq!(
            trie.censor("That wh0re gave m3 a very good H4nd j0b, dude.", '*'),
            "That **** gave m3 a very good ****, dude."
        );
    }

    #[test]
    fn unicode_and_infix_cases() {
        let trie = ProfanityTrie::from_words(
            ["хайль", "противоя́дия", "употребле́ния", "câu", "bậy", "gâu"]
                .into_iter()
                .map(|s| s.to_string()));
        assert_eq!(
            trie.censor("соседский мальчик сказал хайль и я опешил.", '*'),
            "соседский мальчик сказал **** и я опешил."
        );
        assert_eq!(
            trie.censor("Эффекти́вного противоя́дия от я́да фу́гу не существу́ет до сих пор", '*'),
            "Эффекти́вного **** от я́да фу́гу не существу́ет до сих пор"
        );
        assert_eq!(
            trie.censor("...противоя́дия...hello_cat_употребле́ния,,,,qew", '*'),
            "...****...hello_cat_****,,,,qew"
        );
        assert_eq!(
            trie.censor("Đây là 1 câu nói bậy.", '*'),
            "Đây là 1 **** nói ****."
        );
        assert_eq!(
            trie.censor("Con chó sủa gâu gâu!", '*'),
            "Con chó sủa **** ****!"
        );
    }

    #[test]
    fn reload_and_add_keep_existing() {
        let mut trie = ProfanityTrie::from_words(["fuck"].into_iter().map(|s| s.to_string()));
        trie.add_censor_word("supremacia ariana");
        assert_eq!(trie.censor("fuck and heck", '*'), "**** and heck");
        assert_eq!(trie.censor("supremacia ariana", '*'), "****");
        trie.reload(
            ["happy", "merry"].into_iter().map(|s| s.to_string()),
            std::iter::empty::<String>(),
        );
        assert!(!trie.contains_profanity("Fuck you!"));
        assert!(trie.contains_profanity("Have a merry day! :)"));
    }
}
