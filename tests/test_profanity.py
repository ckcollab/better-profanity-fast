#!/usr/bin/env python3
"""better_profanity 0.7-style tests against the published Python API."""

from __future__ import annotations

import os
import statistics
import tempfile
import threading
import time
import unittest
from importlib.resources import files

from better_profanity_fast import WORDLIST_ENV, Profanity


def _wordlist_text():
    return files("better_profanity_fast").joinpath("wordlist.txt").read_text(encoding="utf-8")


def _wordlist_path():
    return os.path.abspath(
        str(files("better_profanity_fast").joinpath("wordlist.txt"))
    )


class ProfanityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profanity = Profanity()

    def setUp(self):
        self.maxDiff = None
        self.profanity.load_censor_words()

    def test_contains_profanity(self):
        self.assertTrue(self.profanity.contains_profanity("he is a m0th3rf*cker"))

    def test_leaves_paragraphs_untouched(self):
        innocent_text = """If you tickle us do we not laugh?
                        If you poison us do we not die?
                        And if you wrong us shall we not revenge?"""
        self.assertEqual(self.profanity.censor(innocent_text), innocent_text)

    def test_empty_string(self):
        self.assertEqual(self.profanity.censor(""), "")

    def test_censorship_1(self):
        censored_text = self.profanity.censor("Dude, I hate shit. Fuck bullshit.")
        self.assertNotIn("shit", censored_text)
        self.assertNotIn("fuck", censored_text)
        self.assertIn("Dude", censored_text)

    def test_censorship_2(self):
        bad_text = "That wh0re gave m3 a very good H4nd j0b, dude. You gotta check."
        censored_text = "That **** gave m3 a very good ****, dude. You gotta check."
        self.assertEqual(self.profanity.censor(bad_text), censored_text)

    def test_censorship_3(self):
        self.assertEqual(
            self.profanity.censor("Those 2 girls 1 cup. You gotta check. "),
            "Those ****. You gotta check. ",
        )

    def test_censorship_4(self):
        self.assertEqual(self.profanity.censor("2 girls 1 cup"), "****")

    def test_censorship_5(self):
        self.assertEqual(self.profanity.censor("fuck 2 girls 1 cup"), "**** ****")

    def test_censorship_with_starting_swear_word(self):
        self.assertEqual(
            self.profanity.censor("  wh0re gave m3 a very good H@nD j0b."),
            "  **** gave m3 a very good ****.",
        )

    def test_censorship_with_ending_swear_word(self):
        self.assertEqual(
            self.profanity.censor("That wh0re gave m3 a very good H@nD j0b."),
            "That **** gave m3 a very good ****.",
        )

    def test_censorship_for_2_words(self):
        censored_text = self.profanity.censor("That wh0re gave m3 a very good H4nd j0b")
        self.assertNotIn("H4nd j0b", censored_text)
        self.assertIn("m3", censored_text)

    def test_censorship_for_clean_text(self):
        self.assertEqual(self.profanity.censor("Hi there"), "Hi there")

    def test_custom_wordlist(self):
        self.profanity.load_censor_words(["happy", "jolly", "merry"])
        self.assertFalse(self.profanity.contains_profanity("Fuck you!"))
        self.assertTrue(self.profanity.contains_profanity("Have a merry day! :)"))

    def test_censorship_without_spaces(self):
        self.assertEqual(
            self.profanity.censor("...pen1s...hello_cat_vagina,,,,qew"),
            "...****...hello_cat_****,,,,qew",
        )

    def test_censorship_inside_concatenated_token(self):
        self.assertTrue(self.profanity.contains_profanity("ThisRetard"))
        self.assertTrue(self.profanity.contains_profanity("RetardToo"))
        self.assertEqual(self.profanity.censor("name ThisRetard please"), "name **** please")
        self.assertFalse(self.profanity.contains_profanity("ThisPenis"))
        self.assertFalse(self.profanity.contains_profanity("stardust"))


class FalsePositiveTests(unittest.TestCase):
    def setUp(self):
        self.profanity = Profanity()

    def test_common_clean_words(self):
        for word in (
            "hello",
            "class",
            "assignment",
            "grass",
            "assume",
            "assistant",
            "document",
            "computer",
        ):
            self.assertFalse(self.profanity.contains_profanity(word), word)
            self.assertEqual(self.profanity.censor(word), word, word)

    def test_short_infix_does_not_match_inside_longer_words(self):
        # penis is 5 letters, tard is 4: both below MIN_INFIX_WORD_LEN (6).
        self.assertFalse(self.profanity.contains_profanity("ThisPenis"))
        self.assertFalse(self.profanity.contains_profanity("stardust"))
        self.assertEqual(self.profanity.censor("ThisPenis stardust"), "ThisPenis stardust")

    def test_public_is_not_pubic(self):
        self.assertFalse(self.profanity.contains_word("public"))
        self.assertFalse(self.profanity.contains_profanity("public"))
        self.assertEqual(self.profanity.censor("a public park"), "a public park")

    def test_lol_dot_i_does_not_become_loli(self):
        text = "lol. I might've kept this"
        self.assertFalse(self.profanity.contains_profanity(text))
        self.assertEqual(self.profanity.censor(text), text)

    def test_pure_numbers_are_not_flagged(self):
        # Digit-only tokens are IDs/years/ports, not leet. Mixed leet (h0mo)
        # and phrases that contain digits (2 girls 1 cup) still match.
        for number in (
            "0",
            "7",
            "69",
            "404",
            "420",
            "911",
            "1011",
            "2026",
            "8080",
            "1234567890",
        ):
            self.assertFalse(self.profanity.contains_word(number), number)
            self.assertFalse(self.profanity.contains_profanity(number), number)
            self.assertEqual(self.profanity.censor(number), number, number)

        for text in (
            "order 1011",
            "id:911",
            "year 2026",
            "ticket #404",
            "10.11.0.1",
            "call 555 1212",
        ):
            self.assertFalse(self.profanity.contains_profanity(text), text)
            self.assertEqual(self.profanity.censor(text), text, text)

        self.assertTrue(self.profanity.contains_profanity("2 girls 1 cup"))
        self.assertTrue(self.profanity.contains_profanity("h0mo"))

    def test_incomplete_leet_does_not_match(self):
        self.assertTrue(self.profanity.contains_word("f*ck"))
        self.assertFalse(self.profanity.contains_word("fck"))

    def test_infix_only_at_six_plus_letters(self):
        self.assertTrue(self.profanity.contains_profanity("ThisRetard"))
        self.assertFalse(self.profanity.contains_profanity("ThisPenis"))
        self.assertFalse(self.profanity.contains_profanity("ThisFuck"))
        self.assertFalse(self.profanity.contains_profanity("fuckbaby"))
        self.assertFalse(self.profanity.contains_profanity("stardust"))
        self.assertFalse(self.profanity.contains_profanity("drape"))

    def test_stretch_matches_without_short_false_positives(self):
        self.assertTrue(self.profanity.contains_profanity("peenis"))
        self.assertTrue(self.profanity.contains_profanity("peniis"))
        self.assertTrue(self.profanity.contains_profanity("pussssy"))
        self.assertFalse(self.profanity.contains_profanity("good"))
        self.assertFalse(self.profanity.contains_profanity("public"))

    def test_assessment_and_class_are_not_ass(self):
        self.assertFalse(self.profanity.contains_profanity("assessment"))
        self.assertFalse(self.profanity.contains_profanity("class"))
        self.assertEqual(self.profanity.censor("assessment class"), "assessment class")


class WhitespaceJoinTests(unittest.TestCase):
    def setUp(self):
        self.filt = Profanity([])
        self.filt.load_censor_words(
            ["loli", "fuck", "shit", "hand job", "ass-pirate", "ball sack"],
            whitelist_words=["lol"],
        )

    def test_loli_itself_matches(self):
        self.assertTrue(self.filt.contains_profanity("loli"))
        self.assertTrue(self.filt.contains_profanity("l0li"))
        self.assertTrue(self.filt.contains_profanity("l0l1"))

    def test_obfuscated_dot_without_space_matches(self):
        self.assertTrue(self.filt.contains_profanity("lol.i"))
        self.assertTrue(self.filt.contains_profanity("lol.i x"))
        self.assertTrue(self.filt.contains_profanity("lol.I"))

    def test_sentence_lol_period_space_i_is_clean(self):
        cases = [
            "lol. I",
            "lol. I might",
            "lol I",
            "lol.  I",
            "lol.\nI",
            "hello lol. I there",
            (
                "the white marks when I marbled her lol. I might've kept this "
                "if the overcoat wasn't pomegranate"
            ),
        ]
        for text in cases:
            self.assertFalse(self.filt.contains_profanity(text), text)
            self.assertEqual(self.filt.censor(text), text, text)

    def test_whitelist_lol_does_not_block_loli(self):
        self.assertEqual(self.filt.censor("lol"), "lol")
        self.assertTrue(self.filt.contains_profanity("loli"))

    def test_phrases_still_join_across_spaces(self):
        self.assertEqual(self.filt.censor("hand job"), "****")
        self.assertEqual(self.filt.censor("hello hand job there"), "hello **** there")
        self.assertEqual(self.filt.censor("ball sack"), "****")
        self.assertEqual(self.filt.censor("ass-pirate"), "****")

    def test_numeric_ids_are_not_loli(self):
        for text in ["1011", "Xor (#101111)", "Xor (#101011)", "cat1011"]:
            self.assertFalse(self.filt.contains_profanity(text), text)
            self.assertEqual(self.filt.censor(text), text, text)


class WordlistOverrideTests(unittest.TestCase):
    def test_env_wordlist_replaces_packaged_list(self):
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".txt", delete=False
        )
        try:
            handle.write("kittens\n")
            handle.close()
            previous = os.environ.get(WORDLIST_ENV)
            os.environ[WORDLIST_ENV] = handle.name
            try:
                filt = Profanity()
                self.assertTrue(filt.contains_profanity("kittens"))
                self.assertFalse(filt.contains_profanity("shit"))
            finally:
                if previous is None:
                    os.environ.pop(WORDLIST_ENV, None)
                else:
                    os.environ[WORDLIST_ENV] = previous
        finally:
            os.unlink(handle.name)

    def test_env_wordlist_missing_file(self):
        previous = os.environ.get(WORDLIST_ENV)
        os.environ[WORDLIST_ENV] = "not_a_real_wordlist_path.txt"
        try:
            with self.assertRaises(FileNotFoundError):
                Profanity()
        finally:
            if previous is None:
                os.environ.pop(WORDLIST_ENV, None)
            else:
                os.environ[WORDLIST_ENV] = previous


class ProfanityApiTests(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.profanity = Profanity()

    def test_custom_words(self):
        self.profanity.add_censor_words(["supremacia ariana"])
        self.assertEqual(self.profanity.censor("supremacia ariana"), "****")

    def test_custom_words_doesnt_remove_initial_words(self):
        self.profanity.add_censor_words(["supremacia ariana"])
        self.assertEqual(self.profanity.censor("fuck and heck"), "**** and heck")

    def test_init_with_list(self):
        custom_badwords = ["happy", "jolly", "merry"]
        Profanity(custom_badwords)
        Profanity(set(custom_badwords))
        Profanity(tuple(custom_badwords))

    def test_init_with_bad_type(self):
        with self.assertRaises(TypeError):
            Profanity(123)
        with self.assertRaises(TypeError):
            Profanity(False)

    def test_punctuation(self):
        self.assertEqual(
            self.profanity.censor("Holy shit! Oh fuck, damn. What the hell? Shut up, asshole..."),
            "Holy ****! Oh ****, ****. What the ****? Shut up, ****...",
        )

    def test_all_default_words(self):
        for word in _wordlist_text().splitlines():
            word = word.strip()
            if word:
                self.assertEqual(self.profanity.censor(word)[:4], "****", word)
                self.assertTrue(self.profanity.contains_profanity(word), word)


class UnicodeRussianTests(unittest.TestCase):
    def setUp(self):
        self.profanity = Profanity([])

    def test_unicode_censorship(self):
        self.profanity.load_censor_words(["хайль"])
        self.assertEqual(
            self.profanity.censor("соседский мальчик сказал хайль и я опешил."),
            "соседский мальчик сказал **** и я опешил.",
        )

    def test_unicode_censorship_2(self):
        self.profanity.load_censor_words(["противоя́дия"])
        self.assertEqual(
            self.profanity.censor(
                "Эффекти́вного противоя́дия от я́да фу́гу не существу́ет до сих пор"
            ),
            "Эффекти́вного **** от я́да фу́гу не существу́ет до сих пор",
        )

    def test_unicode_censorship_3(self):
        self.profanity.load_censor_words(["противоя́дия", "употребле́ния"])
        bad_text = (
            "Эффекти́вного противоя́дия от я́да фу́гу не существу́ет до сих пор. "
            "Но э́то не остана́вливает люде́й от употребле́ния блюд из ры́бы фу́гу."
        )
        censored_text = (
            "Эффекти́вного **** от я́да фу́гу не существу́ет до сих пор. "
            "Но э́то не остана́вливает люде́й от **** блюд из ры́бы фу́гу."
        )
        self.assertEqual(self.profanity.censor(bad_text), censored_text)

    def test_unicode_censorship_4(self):
        self.profanity.load_censor_words(["противоя́дия", "употребле́ния"])
        self.assertEqual(
            self.profanity.censor("...противоя́дия...hello_cat_употребле́ния,,,,qew"),
            "...****...hello_cat_****,,,,qew",
        )

    def test_unicode_censorship_5(self):
        self.profanity.load_censor_words(["шесто́м", "Нидерла́ндах", "перее́хала", "та́нцы"])
        bad_text = (
            "Маргаре́та (э́то бы́ло её настоя́щее и́мя) родила́сь в 1876 "
            "(ты́сяча восемьсо́т се́мьдесят шесто́м) году́ в Нидерла́ндах. "
            "В 18 (восемна́дцать) лет Маргаре́та вы́шла за́муж и перее́хала в Индоне́зию. "
            "Там она́ изуча́ла ме́стную культу́ру и та́нцы."
        )
        censored_text = (
            "Маргаре́та (э́то бы́ло её настоя́щее и́мя) родила́сь в 1876 "
            "(ты́сяча восемьсо́т се́мьдесят ****) году́ в ****. "
            "В 18 (восемна́дцать) лет Маргаре́та вы́шла за́муж и **** в Индоне́зию. "
            "Там она́ изуча́ла ме́стную культу́ру и ****."
        )
        self.assertEqual(self.profanity.censor(bad_text), censored_text)


class UnicodeVietnameseTests(unittest.TestCase):
    def setUp(self):
        self.profanity = Profanity([])

    def test_unicode_vietnamese_1(self):
        self.profanity.load_censor_words(["câu", "bậy"])
        self.assertEqual(
            self.profanity.censor("Đây là 1 câu nói bậy."),
            "Đây là 1 **** nói ****.",
        )

    def test_unicode_vietnamese_2(self):
        self.profanity.load_censor_words(["gâu"])
        self.assertEqual(
            self.profanity.censor("Con chó sủa gâu gâu!"),
            "Con chó sủa **** ****!",
        )


class WhitelistTests(unittest.TestCase):
    def setUp(self):
        self.profanity = Profanity()

    def test_whitelist_words(self):
        bad_text = "I have boobs"
        self.assertEqual(self.profanity.censor(bad_text), "I have ****")
        self.profanity.load_censor_words(whitelist_words=["boobs"])
        self.assertEqual(self.profanity.censor(bad_text), bad_text)


class FileTests(unittest.TestCase):
    def test_read_wordlist_not_found(self):
        with self.assertRaises(FileNotFoundError):
            Profanity([]).load_censor_words_from_file("not_found_file.txt")

    def test_init_wordlist_not_found(self):
        with self.assertRaises(FileNotFoundError):
            Profanity("not_found_file.txt")

    def test_init_from_packaged_wordlist_file(self):
        filt = Profanity(_wordlist_path())
        self.assertTrue(filt.contains_profanity("shit"))


class LargeCorpusTests(unittest.TestCase):
    def setUp(self):
        self.profanity = Profanity()

    def test_0per_paragraph(self):
        good_text = (
            "Veniam sed do pariatur irure deserunt. Et fugiat sint reprehenderit eiusmod magna. "
            "Deserunt occaecat officia eu quis. Velit laborum enim nulla laborum tempor ad. "
            "Amet culpa veniam nisi reprehenderit officia, elit ullamco exercitation do, "
            "incididunt qui voluptate quis incididunt. Tempor culpa ea amet ipsum, dolore quis "
            "proident pariatur. Laborum reprehenderit ad eiusmod proident irure dolor, fugiat "
            "qui aute aute et dolor aliqua. Ullamco fugiat deserunt aliqua consequat sit "
            "proident consectetur, qui nulla excepteur sit. Occaecat dolor sed occaecat "
            "cupidatat labore quis incididunt. Sit ex aute fugiat cupidatat reprehenderit."
        )
        self.assertEqual(self.profanity.censor(good_text), good_text)
        self.assertFalse(self.profanity.contains_profanity(good_text))

    def test_5per_paragraph(self):
        bad_text = (
            "G@*k do dolore sunt exercitation do cillum, adipiscing mollit sit qui sit. "
            "Nulla ea aliquip sed non, exercitation in officia exercitation sed. Velit "
            "aliquip eiusmod ut est ad, ullamco ex veniam aliqua exercitation eiusmod "
            "excepteur, minim sint aliquip adipiscing sit. Quis cupidatat nulla laboris "
            "sit ex, eiusmod aliquip labore $hagg3r labore duis. Amet ut excepteur fugiat "
            "tempor exercitation ipsum. Ipsum nulla commodo aliqua veniam sit consequat "
            "aliqua, nostrud exercitation deserunt ut dolore adipiscing duis et. Et "
            "officia elit occaecat pariatur sed. G*dd*mn*d labore deserunt ad. Nostrud "
            "non non ea irure, ex cupidatat fugiat do nostrud enim veniam. Sint consequat "
            "consectetur in exercitation, dolore occaecat aute sed."
        )
        censored_text = (
            "**** do dolore sunt exercitation do cillum, adipiscing mollit sit qui sit. "
            "Nulla ea aliquip sed non, exercitation in officia exercitation sed. Velit "
            "aliquip eiusmod ut est ad, ullamco ex veniam aliqua exercitation eiusmod "
            "excepteur, minim sint aliquip adipiscing sit. Quis cupidatat nulla laboris "
            "sit ex, eiusmod aliquip labore **** labore duis. Amet ut excepteur fugiat "
            "tempor exercitation ipsum. Ipsum nulla commodo aliqua veniam sit consequat "
            "aliqua, nostrud exercitation deserunt ut dolore adipiscing duis et. Et "
            "officia elit occaecat pariatur sed. **** labore deserunt ad. Nostrud non "
            "non ea irure, ex cupidatat fugiat do nostrud enim veniam. Sint consequat "
            "consectetur in exercitation, dolore occaecat aute sed."
        )
        self.assertEqual(self.profanity.censor(bad_text), censored_text)
        self.assertTrue(self.profanity.contains_profanity(bad_text))

    def test_50per_paragraph(self):
        bad_text = (
            "Exercitation g@ngbangs quis mv7h@ h4ndjob aliqua. T**7 sit enim esse 7e3z "
            "ph*kk3d. Adipiscing f*cknvt quis nisi. Culpa 0p*@7* aliqua sunt laborum "
            "br**s7s, nisi dlckh3ad cillum lorem pariatur. Laborum ex k@ndvm5 mollit "
            "pariatur 571ffy g3y. Amet g3y ipsum $h*t7lng esse lu$ty laboris. Prick duis "
            "pariatur d4mn aute p*5sing minim. Incididunt dolore negro r31ch commodo "
            "feck3r 1vs7 p*cker. Tempor p*nk@ nisi elit, quis h*rdcor*$ex nobh*4d "
            "p*s$y$ thug d1nk phvck, et ipsum culpa f*dgep@ck3r fvckt@rd k@*ch3$ 1ab**."
        )
        censored_text = (
            "Exercitation **** quis **** **** aliqua. **** sit enim esse **** ****. "
            "Adipiscing **** quis nisi. Culpa **** aliqua sunt laborum ****, nisi **** "
            "cillum lorem pariatur. Laborum ex **** mollit pariatur **** ****. Amet **** "
            "ipsum **** esse **** laboris. **** duis pariatur **** aute **** minim. "
            "Incididunt dolore **** **** commodo **** **** ****. Tempor **** nisi elit, "
            "quis **** **** **** **** **** ****, et ipsum culpa **** **** **** ****."
        )
        self.assertEqual(self.profanity.censor(bad_text), censored_text)
        self.assertTrue(self.profanity.contains_profanity(bad_text))

    def test_100per_paragraph(self):
        bad_text = (
            "C@ck5 j1z p*$5e cr0tch u*y**r n@d 5tfu p*5$*ng, g@nj4 m*nstr**71on fvkwhit "
            "f1ngerfucked f*ckwi7 f*kker st1ffy h@mo*r@7*c. Fuck7@rd 2 gir1$ 1 cvp 5hit "
            "7*bglr1 en1*rg3ment perv3r5i*n. Fuckh3ad g*ddam r*mp f*g$ fvcknugge7 "
            "d@gg**57y13. P*wn 1*zzy f*t4n*ry m*thaf*ck*r. Wanky 5tupid bltchin bvc37a, "
            "fuckup pot $h17f*ck*r f*s7f*ck3d f1st3d, mv7h*rfvcker stf* *jacu1*te "
            "thre*$0m* dlck. H@w70mvrd*p phuk5 w@nk*r clpa fuk*r 5h*7* c0cks, c*n7lick*r "
            "k14n *rr5e kumming."
        )
        censored_text = (
            "**** **** **** **** **** **** **** ****, **** **** **** **** **** **** "
            "**** ****. **** **** **** **** **** ****. **** **** **** **** **** ****. "
            "**** **** **** ****. **** **** **** ****, **** **** **** **** ****, **** "
            "**** **** **** ****. **** **** **** **** **** **** ****, **** **** **** ****."
        )
        self.assertEqual(self.profanity.censor(bad_text), censored_text)
        self.assertTrue(self.profanity.contains_profanity(bad_text))


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_contains_and_censor(self):
        filt = Profanity()
        clean = "Hi there friend, how are you doing today?"
        dirty = "Dude, I hate shit. Fuck bullshit."
        errors = []

        def worker():
            try:
                for _ in range(80):
                    if filt.contains_profanity(clean):
                        raise AssertionError("clean text flagged")
                    if not filt.contains_profanity(dirty):
                        raise AssertionError("dirty text missed")
                    if filt.censor(clean) != clean:
                        raise AssertionError("clean text censored")
                    if "shit" in filt.censor(dirty).lower():
                        raise AssertionError("dirty text not censored")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])


class PerformanceTests(unittest.TestCase):
    MAX_MEDIAN_MS = 10.0

    def test_short_paragraph_contains_profanity_under_baseline(self):
        text = (
            "Original: Jasmine/Seabed/Flame/Quartz (I hate white overcoats)\n\n"
            "1. Pomegranate/Licorice/Panda/Nightfall - Shuffled solely so I could see "
            "the white marks when I marbled her lol. I might've kept this if the "
            "overcoat wasn't pomegranate"
        )
        filt = Profanity()
        for _ in range(3):
            filt.contains_profanity(text)
        samples = []
        for _ in range(21):
            start = time.perf_counter()
            filt.contains_profanity(text)
            samples.append((time.perf_counter() - start) * 1000)
        median_ms = statistics.median(samples)
        self.assertLess(
            median_ms,
            self.MAX_MEDIAN_MS,
            "contains_profanity median %.3f ms exceeded %s ms"
            % (median_ms, self.MAX_MEDIAN_MS),
        )


if __name__ == "__main__":
    unittest.main()
