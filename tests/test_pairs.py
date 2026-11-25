"""Row 23 of docs/contract.md: "nobody can know" is proven, and not only said."""

import random
import unittest

from grader import Broken
from grader.pairs import EACH, tells_apart
from tests.world import entry, recording

LETTERS = "abcdefghijklmnopqrstuvwxyz"
FEEDS = "north-web", "north-app", "south-web", "south-app"


def made(seed, refused=3, status=401, missing=(), **line):
    """Somebody is refused a few times. Times, ids and the order of events are never the same."""
    chance = random.Random(seed)
    ids = iter(chance.sample([one + other for one in LETTERS for other in LETTERS], 60))
    at = chance.randint(0, 400)
    found = [entry(f"S-aaaa{next(ids)}", at, "series", name="waiting", value=0)]
    for number in range(refused):
        at += chance.randint(1, 300)
        found.append(entry(f"F-aaaa{next(ids)}", at, "front", feed="north-web", event=f"e{chance.randint(1, 9)}", status=status))
    at += chance.randint(1, 300)
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
        self.assertEqual({one[0] for one in found}, {"how many"})

    def test_23_a_status(self):
        self.assertTrue(tells_apart(many(0), many(100, status=400)))

    def test_23_a_field_that_is_empty(self):
        self.assertTrue(tells_apart(many(0, event="e1"), many(100)))

    def test_23_when_it_happens(self):
        def lost(seed, least):
            return recording(entry("L-aaaaaa", least + random.Random(seed).randint(0, 1000), "log", level="error", what="no_database"))

        self.assertTrue(tells_apart([lost(number, 0) for number in range(EACH)], [lost(100 + number, 5000) for number in range(EACH)]))

    def test_23_what_comes_first(self):
        def two(seed, first):
            chance = random.Random(seed)
            start, gap = chance.randint(0, 1000), chance.randint(1, 1000)
            names = ("kind", "worker"), ("kind", "api")
            one, other = names if first == "worker" else names[::-1]
            end = entry("S-aaaaaa", start + gap + chance.randint(1, 5000), "series", name="waiting", value=0)
            return recording(entry("P-aaaaaa", start, "process", **dict([one])), entry("P-bbbbbb", start + gap, "process", **dict([other])), end)

        workers, apis = [two(number, "worker") for number in range(EACH)], [two(100 + number, "api") for number in range(EACH)]
        self.assertEqual([one[0] for one in tells_apart(workers, apis)], ["before", "before"])

    def test_23_whether_it_is_always_the_same_event(self):
        def refused(seed, same):
            chance = random.Random(seed)
            start = chance.randint(0, 1000)
            return recording(*(entry(f"F-aaaaa{letter}", start + number, "front", event="e1" if same else f"e{number + 1}", status=401) for number, letter in enumerate("abc")))

        self.assertTrue(tells_apart([refused(number, True) for number in range(EACH)], [refused(number, False) for number in range(EACH)]))

    def test_23_a_difference_that_is_spread_over_the_feeds(self):
        def refused(seed, reason):
            chance = random.Random(seed)
            return recording(entry("L-aaaaaa", chance.randint(0, 1000), "log", what="refused", feed=chance.choice(FEEDS), reason=reason))

        times, signatures = ([refused(start + number, reason) for number in range(EACH)] for start, reason in ((0, "wrong_time"), (100, "wrong_signature")))
        self.assertTrue(tells_apart(times, signatures))
        self.assertEqual(tells_apart(times, [refused(200 + number, "wrong_time") for number in range(EACH)]), [])

    def test_23_a_status_between_others(self):
        # The least and the most are the same, and the sum is drawn.
        def asked(seed, status):
            chance = random.Random(seed)
            statuses = [202, status] + [503] * chance.randint(1, 4)
            chance.shuffle(statuses)
            return recording(*(entry(f"F-aaaaa{letter}", at, "front", status=one) for letter, at, one in zip(LETTERS, sorted(chance.sample(range(1000), 6)), statuses)))

        self.assertTrue(tells_apart([asked(number, 400) for number in range(EACH)], [asked(100 + number, 409) for number in range(EACH)]))

    def test_23_how_long_it_is_before_the_end(self):
        def quiet(seed, least):
            chance = random.Random(seed)
            start = chance.randint(0, 100_000)
            return recording(entry("L-aaaaaa", start, "log", what="no_database"), entry("S-aaaaaa", start + least + chance.randint(0, 100), "series", name="waiting", value=0))

        self.assertTrue(tells_apart([quiet(number, 500) for number in range(EACH)], [quiet(100 + number, 5000) for number in range(EACH)]))

    def test_23_how_soon_the_same_one_comes_again(self):
        def twice(seed, least):
            chance = random.Random(seed)
            start = chance.randint(0, 100_000)
            again = start + least + chance.randint(0, 100)
            return recording(
                entry("F-aaaaaa", start, "front", event="e1", status=202), entry("F-bbbbbb", again, "front", event="e1", status=202),
                entry("S-aaaaaa", again + chance.randint(0, 100_000), "series", name="waiting", value=0))

        self.assertTrue(tells_apart([twice(number, 500) for number in range(EACH)], [twice(100 + number, 5000) for number in range(EACH)]))

    def test_23_an_event_that_has_the_one_and_not_the_other(self):
        # There are as many of each, and how many events there are is drawn.
        def handled(seed, last):
            chance = random.Random(seed)
            said = [("stored", one) for one in ("e1", "e2", "e3")] + [("done", one) for one in ("e1", "e2", last)] + [("already", f"e{one}") for one in range(5, 5 + chance.randint(1, 6))]
            chance.shuffle(said)
            times = sorted(chance.sample(range(5000), len(said)))
            return recording(*(entry(f"L-aaaaa{letter}", at, "log", what=what, event=event) for letter, at, (what, event) in zip(LETTERS, times, said)))

        found = tells_apart([handled(number, "e3") for number in range(EACH)], [handled(100 + number, "e4") for number in range(EACH)])
        self.assertEqual({one[0] for one in found}, {"without"})

    def test_23_how_long_the_same_event_takes(self):
        # Other events come again at once, and others very late, so that nothing else shows it.
        def handled(seed, least):
            chance = random.Random(seed)
            start = chance.randint(0, 100_000)
            said = [(start, "stored", "e1"), (start + least + chance.randint(0, 100), "done", "e1")]
            for event, pause in (("e2", 1), ("e3", 300_000)):
                again = chance.randint(0, 100_000)
                said += [(again, "already", event), (again + pause, "already", event)]
            return recording(*(entry(f"L-aaaaa{letter}", at, "log", what=what, event=event) for letter, (at, what, event) in zip(LETTERS, sorted(said))))

        found = tells_apart([handled(number, 100) for number in range(EACH)], [handled(100 + number, 5000) for number in range(EACH)])
        self.assertEqual({one[0] for one in found}, {"soonest after", "latest after"})

    def test_23_a_word_in_a_line_as_it_was_written(self):
        def said(seed, word):
            return recording(entry("L-aaaaaa", random.Random(seed).randint(0, 1000), "log", what="failed"), raw={"L-aaaaaa": f"it {word} 4711 times"})

        self.assertTrue(tells_apart([said(number, "fell") for number in range(EACH)], [said(100 + number, "broke") for number in range(EACH)]))
        self.assertEqual(tells_apart([said(number, "fell") for number in range(EACH)], [said(100 + number, "fell") for number in range(EACH)]), [])

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
