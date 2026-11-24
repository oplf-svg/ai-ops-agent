"""Row 22 of docs/contract.md: a recording does not give its own answer away."""

import unittest

from grader.leaks import WORDS, find
from tests import world
from tests.world import ENDED, entry, recording

CAUSES = ("ended-after", "counted-twice")


def found(text="", names=(), extra=()):
    seen = recording(*ENDED, *extra, raw={"L-stored": text} if text else {})
    return {word for _, word in find(seen, names, CAUSES)}


class Leaks(unittest.TestCase):
    def test_22_nothing_in_a_recording_that_is_right(self):
        self.assertEqual(find(world.recording(), ["worker-1", "api"], CAUSES), [])

    def test_22_every_word_of_the_list(self):
        # The names that the crash tests of webhook-platform use.
        self.assertLessEqual({"doomed", "poison", "forged", "crash", "fault", "bad"}, set(WORDS))
        for word in WORDS:
            for text in (f"a {word} one", f"evt_{word}-3", word.upper(), f"N-{word}"):
                self.assertEqual(found(text), {word}, text)

    def test_22_words_written_together(self):
        self.assertEqual(found("at Platform.FaultPlan.Reach"), {"fault"})
        self.assertEqual(found("notBad"), {"bad"})

    def test_22_words_that_only_look_like_it(self):
        for text in ("by default", "a badge", "wrong signature", "attempt 1 failed", "honestly", "crashed"):
            self.assertEqual(found(text), set(), text)

    def test_22_the_code_of_a_cause(self):
        for text in ("ended-after", "ended_after", "EndedAfter", "it ended after that"):
            self.assertEqual(found(text), {"ended-after"}, text)

    def test_22_names_of_files_and_processes(self):
        self.assertEqual(found(names=["doomed.log", "worker"]), {"doomed"})

    def test_22_the_entries_themselves(self):
        self.assertEqual(found(extra=[entry("L-refuse", 5000, "log", what="refused", feed="bad-shop")]), {"bad"})

    def test_22_it_says_where(self):
        self.assertEqual(find(recording(*ENDED, raw={"L-donebb": "poison"}), [], CAUSES), [("raw L-donebb", "poison")])
