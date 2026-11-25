"""What a score has to be compared with."""

import json
import unittest

from grader.baselines import Search, by_table, compare, heard, report
from grader.causes import read_table
from grader.grade import Case
from tests import world
from tests.world import ENDED, RAW, entry, recording


def said(*lines):
    """A recording with these lines: the level, and what was written."""
    entries = [entry(f"L-aaaaa{'abcdefgh'[number]}", number, "log", level=level, what="other") for number, (level, _) in enumerate(lines)]
    return recording(*entries, raw={one.id: text for one, (_, text) in zip(entries, lines)})


def line(message, problem=None):
    return json.dumps({"Message": message} | ({"Exception": problem} if problem else {}))


class Heard(unittest.TestCase):
    def test_only_the_loud_lines_are_heard(self):
        self.assertEqual(heard(said(("information", line("quiet words")), ("warning", line("a Warning")), ("error", line("loud: 2 errors")))), {"warning", "loud", "errors"})

    def test_an_error_is_heard_up_to_its_first_line(self):
        self.assertEqual(heard(said(("error", line("failed", "Broken: it ended\n   at Somewhere.Inside()")))), {"failed", "broken", "ended"})

    def test_a_line_that_is_no_json(self):
        self.assertEqual(heard(said(("error", "Unhandled problem"), ("error", "[1]"), ("error", '"last words"'))), {"unhandled", "problem", "last", "words"})


SENTENCES = {"row-held": "Somebody held a row that an event needs.", "api-ended": "The program ended.", "shop-silent": "A shop sends nothing, and nobody knows why it is so silent today."}


class Words(unittest.TestCase):
    def name(self, text, sentences=SENTENCES):
        return Search(sentences).name(said(("error", line(text))))

    def test_the_sentence_with_most_in_common(self):
        self.assertEqual([self.name(text) for text in ("the row is held", "the program ended", "silent shop")], ["row-held", "api-ended", "shop-silent"])
        # The first one has a word in common as well, but the second one has more.
        self.assertEqual(self.name("an event, and the program ended"), "api-ended")

    def test_it_is_the_share_of_the_sentence(self):
        # Two words of the long sentence, and one of the two of the short one.
        self.assertEqual(self.name("a shop today: program"), "api-ended")

    def test_a_rare_word_says_more(self):
        sentences = {"one": "Event event row lock.", "two": "Event row gone.", "three": "Event row lost."}
        self.assertEqual(self.name("event row gone", sentences), "two")
        # What stands in every sentence says nothing.
        self.assertEqual(self.name("event row", sentences), "none")

    def test_nothing_in_common(self):
        self.assertEqual(self.name("xyz"), "none")
        self.assertEqual(Search(SENTENCES).name(said(("information", line("the row is held")))), "none")

    def test_the_first_of_two_that_are_alike(self):
        sentences = {"one": "Lock gone.", "two": "Gone lock.", "three": "Other."}
        self.assertEqual(self.name("lock", sentences), "one")


class TheTable(unittest.TestCase):
    def test_the_only_cause_that_can_be_shown(self):
        table = read_table("ended-after: One.\n  process exit=137 say exit\nended-before: Two.\n  process exit=1 say exit\n")
        self.assertEqual(by_table(table, recording()), "ended-after")

    def test_two_that_can_be_shown_are_none(self):
        table = read_table("ended-after: One.\n  process exit=137 say exit\nended-before: Two.\n  process kind=worker say kind\n")
        self.assertEqual(by_table(table, recording()), "none")
        self.assertEqual(by_table(read_table("ended-after: One.\n  process exit=1 say exit\n"), recording()), "none")


FAILURES = [(Case("c1", "failure", "ended-after"), recording()), (Case("c2", "failure", "refused-often"), recording(*ENDED[:4], raw={})), (Case("n1", "failure", "none"), recording(*ENDED[:1], raw={}))]


class Compared(unittest.TestCase):
    def test_each_alone_and_both_kinds_apart(self):
        self.assertEqual(compare(world.table(), FAILURES), {'always "I don\'t know"': (0, 1), "a search for words": (0, 1), "the table itself": (1, 1)})
        loud = recording(*ENDED, entry("L-loudly", 9000, "log", level="error", what="other"), raw=RAW | {"L-loudly": line("a worker ended after its work was committed, and before it said so")})
        self.assertEqual(compare(world.table(), [(Case("c1", "failure", "ended-after"), loud)])["a search for words"], (1, 0))

    def test_the_report(self):
        self.assertEqual(report(world.table(), FAILURES).split("\n")[0], "| Baseline, without a model | right of 2 whose cause can be known | right of 1 that nobody can know |")
        self.assertIn("| the table itself | 1 | 1 |\n", report(world.table(), FAILURES))
