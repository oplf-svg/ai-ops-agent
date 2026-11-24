"""Row 23 of docs/contract.md: "nobody can know" is proven, and not only said."""

import random
import unittest

from grader import Broken
from grader.pairs import EACH, tells_apart
from tests.world import entry, recording

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def made(seed, refused=3, status=401, late=0, missing=(), **line):
    """Somebody is refused a few times. Times, ids and the order of events are never the same."""
    chance = random.Random(seed)
    ids = iter(chance.sample([one + other for one in LETTERS for other in LETTERS], 60))
    at = chance.randint(0, 400)
    found = [entry(f"S-aaaa{next(ids)}", at, "series", name="waiting", value=0)]
    for number in range(refused):
        at += chance.randint(1, 300)
        found.append(entry(f"F-aaaa{next(ids)}", at, "front", feed="north-web", event=f"e{chance.randint(1, 9)}", status=status))
    at += chance.randint(1, 300) + late
    values = {"process": "p1", "level": "warning", "what": "refused", "feed": "north-web", "reason": "wrong_signature", "number": refused} | line
    found.append(entry(f"L-aaaa{next(ids)}", at, "log", **values))
    for number in range(chance.randint(1, 4)):
        at += chance.randint(1, 300)
        found.append(entry(f"S-aaaa{next(ids)}", at, "series", name="waiting", value=chance.randint(0, 2)))
    return recording(*found, missing=missing)


def many(start, many=EACH, **how):
    return [made(start + number, **how) for number in range(many)]


class Pairs(unittest.TestCase):
    def test_23_two_causes_that_look_the_same(self):
        self.assertEqual(tells_apart(many(0), many(100)), [])

    def test_23_a_word(self):
        self.assertTrue(tells_apart(many(0), many(100, reason="wrong_time")))

    def test_23_a_number_in_a_line(self):
        self.assertTrue(tells_apart(many(0), many(100, number=4)))

    def test_23_how_many_there_are(self):
        self.assertTrue(tells_apart(many(0), many(100, refused=4, number=3)))

    def test_23_only_how_many_there_are(self):
        def lines(seed, how_many):
            chance = random.Random(seed)
            times = sorted(chance.sample(range(1000), how_many))
            return recording(*(entry(f"L-aaaaa{letter}", at, "log", level="error", what="no_database") for letter, at in zip(LETTERS, times)))

        found = tells_apart([lines(number, 3) for number in range(EACH)], [lines(100 + number, 4) for number in range(EACH)])
        self.assertEqual([one[0] for one in found], ["how many"])

    def test_23_a_status(self):
        self.assertTrue(tells_apart(many(0), many(100, status=400)))

    def test_23_a_field_that_is_empty(self):
        self.assertTrue(tells_apart(many(0, event="e1"), many(100)))

    def test_23_when_it_happens(self):
        self.assertTrue(tells_apart(many(0), many(100, late=5_000)))

    def test_23_what_comes_first(self):
        def two(seed, first):
            chance = random.Random(seed)
            start, gap = chance.randint(0, 1000), chance.randint(1, 1000)
            names = ("kind", "worker"), ("kind", "api")
            one, other = names if first == "worker" else names[::-1]
            return recording(entry("P-aaaaaa", start, "process", **dict([one])), entry("P-bbbbbb", start + gap, "process", **dict([other])))

        workers, apis = [two(number, "worker") for number in range(EACH)], [two(100 + number, "api") for number in range(EACH)]
        self.assertEqual([one[0] for one in tells_apart(workers, apis)], ["before", "before"])

    def test_23_whether_it_is_always_the_same_event(self):
        def refused(seed, same):
            chance = random.Random(seed)
            start = chance.randint(0, 1000)
            return recording(*(entry(f"F-aaaaa{letter}", start + number, "front", event="e1" if same else f"e{number + 1}", status=401) for number, letter in enumerate("abc")))

        self.assertTrue(tells_apart([refused(number, True) for number in range(EACH)], [refused(number, False) for number in range(EACH)]))

    def test_23_a_source_that_is_missing(self):
        self.assertTrue(tells_apart(many(0), many(100, missing=[("log", 0, 10)])))

    def test_23_an_entry_that_only_one_of_them_has(self):
        more = [recording(*one.entries, entry("P-aaaaaa", 90_000, "process", process="p1", kind="worker", exit=1)) for one in many(100)]
        found = tells_apart(many(0), more)
        self.assertTrue(any("process" in repr(one) for one in found))

    def test_23_which_event_or_process_it_was_does_not_matter(self):
        self.assertEqual(tells_apart(many(0, process="p1"), many(100, process="p7")), [])

    def test_23_one_that_looks_like_the_others_is_enough(self):
        # Seven of eight are different. Whoever sees the eighth cannot know.
        self.assertEqual(tells_apart(many(0), [*many(100, 7, number=4), *many(200, 1)]), [])

    def test_23_too_few_recordings(self):
        for these, those in ((many(0, EACH - 1), many(100)), (many(0), many(100, EACH - 1))):
            with self.assertRaisesRegex(Broken, "needs 8 recordings"):
                tells_apart(these, those)
