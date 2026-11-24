"""Rows 8, 9 and 19 of docs/contract.md: what a cause needs, and that the table tells the recordings apart."""

import itertools
import unittest

from grader import Broken
from grader.causes import read_table
from grader.gate import ENOUGH
from grader.grade import Case, check_table
from tests import world
from tests.world import CALLS, DONE, ENDED, EXIT, SILENT, call, claim, entry, graded, named, recording, says, search

WORKER = "ended-after: A worker ended.\n"
TWICE = (*ENDED, entry("R-orderc", 4000, "row", table="orders", shop="north", order="o1", event="e1", item="i1", quantity=1, cents=500))
REFUSED = tuple(entry(f"F-forge{letter}", at, "front", feed="north-web", status=401) for letter, at in zip("abc", (10, 20, 30))) + (
    entry("L-refuse", 40, "log", process="p1", level="warning", what="refused", feed="north-web", reason="wrong_signature", number=3),
    entry("L-refusd", 50, "log", process="p1", level="warning", what="refused", feed="south-web", reason="wrong_signature", number=1))


def result(claims, cause="ended-after", calls=CALLS, **more):
    found = graded(named(cause, claims), calls, truth=cause, **more)
    return found.outcome, found.step


CAUGHT = ("caught", ENOUGH)


class Enough(unittest.TestCase):
    def test_08_all_that_is_needed(self):
        for claims in itertools.permutations((EXIT, DONE, SILENT)):
            self.assertEqual(result(claims), ("right", ""))

    def test_08_each_line_is_needed(self):
        for claims in ((DONE, SILENT), (EXIT, SILENT), (EXIT, DONE), (EXIT,)):
            self.assertEqual(result(claims), CAUGHT)

    def test_08_what_has_to_be_said_has_to_be_said(self):
        # It is the right entry, and what is said about it is true. It is only not what matters.
        self.assertEqual(result((EXIT, says("row", "R-inboxa", "attempts", "1"), SILENT)), CAUGHT)
        self.assertEqual(result((says("process", "P-worker", "kind", "worker"), DONE, SILENT)), CAUGHT)

    def test_08_all_of_what_has_to_be_said(self):
        table = read_table(WORKER + "  row table=inbox state=done attempts=1 say state,attempts\n")
        tries = says("row", "R-inboxa", "attempts", "1")
        self.assertEqual(result((DONE,), with_table=table), CAUGHT)
        self.assertEqual(result((tries,), with_table=table), CAUGHT)
        self.assertEqual(result((DONE, tries), with_table=table), ("right", ""))

    def test_08_one_of_several_values(self):
        table = read_table(WORKER + "  row table=inbox state=aside|done attempts=1 say state\n")
        self.assertEqual(result((DONE,), with_table=table), ("right", ""))
        table = read_table(WORKER + "  row table=inbox state=aside|waiting attempts=1 say state\n")
        self.assertEqual(result((DONE,), with_table=table), CAUGHT)
        table = read_table(WORKER + "  process exit=none|1 kind=worker say exit\n")
        self.assertEqual(result((says("process", "P-nextwo", "exit", "none"),), with_table=table), ("right", ""))

    def test_08_what_was_not_named_does_not_count(self):
        shown = [call("list_processes", "P-worker", "P-theapi"), call("get_row", "R-inboxa", "R-inboxb"), CALLS[2]]
        self.assertEqual(result((says("process", "P-theapi", "exit", "none"), DONE, SILENT), calls=shown), CAUGHT)

    def test_08_the_same_everywhere(self):
        # The row of e2, and the silence about e1.
        shown = [call("list_processes", "P-worker"), call("get_row", "R-inboxb"), CALLS[2]]
        self.assertEqual(result((EXIT, says("row", "R-inboxb", "state", "done"), SILENT), calls=shown), CAUGHT)

    def test_08_the_same_in_two_entries(self):
        table = read_table(WORKER + "  row table=inbox event=$e say event\n  row table=orders event=$e say event\n")
        row, its, of_another = says("row", "R-inboxa", "event", "e1"), says("row", "R-ordera", "event", "e1"), says("row", "R-orderb", "event", "e2")
        shown = [call("get_history", "R-inboxa", "R-ordera", "R-orderb")]
        self.assertEqual(result((row, its), calls=shown, with_table=table), ("right", ""))
        self.assertEqual(result((row, of_another), calls=shown, with_table=table), CAUGHT)

    def test_08_a_row_that_does_not_fit_every_condition(self):
        seen = recording(*[one if one.id != "R-inboxa" else entry("R-inboxa", 4000, "row", table="inbox", event="e1", state="done", attempts=3) for one in ENDED])
        self.assertEqual(result(world.RIGHT, in_recording=seen), CAUGHT)

    def test_08_then_means_not_before(self):
        late = [one for one in ENDED if one.id != "P-worker"] + [entry("P-worker", 4001, "process", process="p2", kind="worker", exit=137)]
        self.assertEqual(result(world.RIGHT, in_recording=recording(*late)), CAUGHT)
        same = [one for one in ENDED if one.id != "P-worker"] + [entry("P-worker", 4000, "process", process="p2", kind="worker", exit=137)]
        self.assertEqual(result(world.RIGHT, in_recording=recording(*same)), ("right", ""))

    def test_08_a_wider_absence_is_enough_and_a_narrower_one_is_not(self):
        wider = claim("none", "log", "Q-widest", event="e9")
        table = read_table(WORKER + "  row table=inbox event=$e state=done say state\n  no log what=failed event=$e\n")
        quiet = [one for one in ENDED if one.id != "L-stored"]
        everything = claim("none", "log", "Q-silent", event="e1")
        self.assertEqual(result((DONE, everything), calls=[CALLS[1], search("Q-silent", "log", event="e1")], in_recording=recording(*quiet), with_table=table), ("right", ""))
        narrow = claim("none", "log", "Q-narrow", what="failed", event="e1", process="p3")
        self.assertEqual(result((DONE, narrow), calls=[CALLS[1], search("Q-narrow", "log", what="failed", event="e1", process="p3")], with_table=table), CAUGHT)
        self.assertEqual(result((DONE, wider), calls=[CALLS[1], search("Q-widest", "log", event="e9")], with_table=table), CAUGHT)

    def test_08_an_absence_in_another_source(self):
        absent = claim("none", "front", "Q-fronts", feed="south-web")
        table = read_table(WORKER + "  process exit=137 say exit\n  no log feed=south-web\n")
        self.assertEqual(result((EXIT, absent), calls=[CALLS[0], search("Q-fronts", "front", feed="south-web")], with_table=table), CAUGHT)

    def test_08_so_many_by_a_count(self):
        row = says("row", "R-inboxa", "event", "e1")
        shown = [call("get_row", "R-inboxa"), search("Q-orders", "row", table="orders", event="e1")]
        count = claim("count", "row", "Q-orders", value="2", table="orders", event="e1")
        self.assertEqual(result((row, count), "counted-twice", shown, in_recording=recording(*TWICE)), ("right", ""))
        self.assertEqual(result((row, count | {"value": "1"}), "counted-twice", shown), CAUGHT)

    def test_08_so_many_by_naming_them(self):
        row, one, other = says("row", "R-inboxa", "event", "e1"), says("row", "R-ordera", "order", "o1"), says("row", "R-orderc", "order", "o1")
        shown = [call("get_history", "R-inboxa", "R-ordera", "R-orderb", "R-orderc")]
        self.assertEqual(result((row, one, other), "counted-twice", shown, in_recording=recording(*TWICE)), ("right", ""))
        self.assertEqual(result((row, one), "counted-twice", shown, in_recording=recording(*TWICE)), CAUGHT)
        # The same entry twice is one entry, and an order of another event does not count.
        self.assertEqual(result((row, one, one, says("row", "R-ordera", "cents", "500")), "counted-twice", shown, in_recording=recording(*TWICE)), CAUGHT)
        self.assertEqual(result((row, one, says("row", "R-orderb", "order", "o2")), "counted-twice", shown, in_recording=recording(*TWICE)), CAUGHT)

    def test_08_a_count_of_something_narrower_is_enough_and_of_something_wider_is_not(self):
        row = says("row", "R-inboxa", "event", "e1")
        narrow = claim("count", "row", "Q-orders", value="2", table="orders", event="e1", shop="north")
        self.assertEqual(result((row, narrow), "counted-twice", [CALLS[1], search("Q-orders", "row", table="orders", event="e1", shop="north")], in_recording=recording(*TWICE)), ("right", ""))
        wide = claim("count", "row", "Q-orders", value="3", table="orders")
        self.assertEqual(result((row, wide), "counted-twice", [CALLS[1], search("Q-orders", "row", table="orders")], in_recording=recording(*TWICE)), CAUGHT)

    def test_08_each_line_needs_an_entry_of_its_own(self):
        table = read_table(WORKER + "  row table=orders event=$e order=$o say order\n  row table=orders event=$e order=$o say order\n")
        one, other = says("row", "R-ordera", "order", "o1"), says("row", "R-orderc", "order", "o1")
        shown = [call("get_history", "R-ordera", "R-orderc")]
        self.assertEqual(result((one, other), calls=shown, in_recording=recording(*TWICE), with_table=table), ("right", ""))
        self.assertEqual(result((one,), calls=shown, in_recording=recording(*TWICE), with_table=table), CAUGHT)

    def test_08_it_looks_for_another_entry_if_the_first_does_not_lead_on(self):
        # Two rows fit the second line. Only the second of them has the silence that the third line needs.
        table = read_table(WORKER + "  row table=inbox event=$e state=done say state\n  no log what=done event=$e\n")
        quiet = search("Q-nodone", "log", what="done", event="e1")
        seen = [one for one in ENDED if one.id not in ("R-inboxa", "R-inboxb")] + [
            entry("R-inboxb", 4000, "row", table="inbox", event="e2", state="done"), entry("R-inboxa", 4000, "row", table="inbox", event="e1", state="done")]
        claims = (says("row", "R-inboxb", "state", "done"), DONE, SILENT)
        self.assertEqual(result(claims, calls=[call("get_row", "R-inboxa", "R-inboxb"), quiet], in_recording=recording(*seen), with_table=table), ("right", ""))

    def test_08_an_empty_field_is_not_the_same_as_another_empty_field(self):
        table = read_table(WORKER + "  front event=$e status=401 say status\n  row table=inbox event=$e say table\n")
        seen = recording(entry("F-noeven", 1, "front", feed="north-web", status=401), entry("R-noeven", 2, "row", table="inbox"))
        claims = (says("front", "F-noeven", "status", "401"), says("row", "R-noeven", "table", "inbox"))
        self.assertEqual(result(claims, calls=[call("get_row", "F-noeven", "R-noeven")], in_recording=seen, with_table=table), CAUGHT)

    def test_08_a_number_that_is_one_too_small(self):
        refused = says("log", "L-refuse", "reason", "wrong_signature")
        shown = [call("search", "L-refuse", input={"source": "log", "where": [{"field": "what", "value": "refused"}], "from": "none", "to": "none"}, search="Q-refuse"), search("Q-fronts", "front", feed="north-web", status="401")]
        count = claim("count", "front", "Q-fronts", value="3", feed="north-web", status="401")
        self.assertEqual(result((refused, count), "refused-often", shown, in_recording=recording(*REFUSED)), ("right", ""))
        fewer = recording(*REFUSED[1:])
        self.assertEqual(result((refused, count | {"value": "2"}), "refused-often", shown, in_recording=fewer), CAUGHT)

    def test_09_a_cause_that_nothing_can_prove(self):
        for claims in (world.RIGHT, (EXIT,), (*world.RIGHT, says("process", "P-theapi", "kind", "api"))):
            self.assertEqual(result(claims, "key-was-made-up"), CAUGHT)
        self.assertEqual(graded(named("key-was-made-up"), truth="none").outcome, "caught")


class Possible(unittest.TestCase):
    def test_19_the_table_tells_the_recordings_apart(self):
        cases = [(Case("c1", "failure", "ended-after"), recording()), (Case("c2", "failure", "counted-twice"), recording(*TWICE)), (Case("c3", "failure", "refused-often"), recording(*REFUSED))]
        self.assertEqual(check_table(world.table(), cases[2:]), [])
        self.assertEqual(check_table(world.table(), cases[:2]), ["c2: ended-after could be shown as well"])

    def test_19_only_a_complete_table_can_tell_them_apart(self):
        table = read_table(WORKER + "other-one: Something else.\n  process exit=137 say exit\n")
        with self.assertRaisesRegex(Broken, "does not say yet what these need: ended-after"):
            check_table(table, [(Case("c1", "failure", "other-one"), recording())])

    def test_19_the_right_cause_cannot_be_shown(self):
        self.assertEqual(check_table(world.table(), [(Case("c1", "failure", "ended-before"), recording())]), ["c1: ended-after could be shown as well", "c1: ended-before cannot be shown"])

    def test_19_where_nothing_can_be_known_nothing_may_be_possible(self):
        self.assertEqual(check_table(world.table(), [(Case("n1", "failure", "none"), recording(*REFUSED[:2]))]), [])
        self.assertEqual(check_table(world.table(), [(Case("n1", "failure", "none"), recording())]), ["n1: ended-after could be shown as well"])

    def test_19_an_absence_in_a_gap_cannot_be_shown(self):
        self.assertEqual(world.table().possible(recording()), {"ended-after"})
        self.assertEqual(world.table().possible(recording(*ENDED, missing=[("log", 0, 1)])), set())

    def test_19_a_number_that_is_reached_in_spite_of_a_gap_can_be_shown(self):
        self.assertEqual(world.table().possible(recording(*REFUSED, missing=[("front", 5, 6)])), {"refused-often"})

    def test_19_whatever_gets_through_is_possible(self):
        """Every answer with some of the true claims: what the table lets through is never more than what it says is possible."""
        claims = [EXIT, DONE, SILENT, says("row", "R-inboxb", "state", "done"), says("row", "R-inboxa", "event", "e1"), says("row", "R-ordera", "event", "e1"), says("row", "R-orderc", "event", "e1")]
        calls = [call("get_history", "P-worker", "R-inboxa", "R-inboxb", "R-ordera", "R-orderc"), CALLS[2]]
        through = set()
        for size in range(1, len(claims) + 1):
            for some in itertools.combinations(claims, size):
                for cause in world.table().causes:
                    if result(some, cause, calls, in_recording=recording(*TWICE)) == ("right", ""):
                        through.add(cause)
        self.assertEqual(through, {"ended-after", "counted-twice"})
        self.assertEqual(through, world.table().possible(recording(*TWICE)))


class Reading(unittest.TestCase):
    def broken(self, text, why):
        with self.subTest(text=text), self.assertRaisesRegex(Broken, why):
            read_table(text)

    def test_08_causes_and_sentences(self):
        table = read_table("# a remark\n\n" + WORKER + "\n  # another\n  process exit=137 say exit\nnever-known: Nobody knows.\n  never\n")
        self.assertEqual(table.causes, ("ended-after", "never-known"))
        self.assertEqual(table.sentences["never-known"], "Nobody knows.")
        self.assertEqual(table.open, ())

    def test_08_a_cause_for_which_nobody_has_written_anything(self):
        table = read_table(WORKER + "other-one: Something else.\n  process exit=137 say exit\n")
        self.assertEqual(table.open, ("ended-after",))
        with self.assertRaisesRegex(Broken, "nobody has written yet what ended-after needs"):
            graded(named(), truth="ended-after", with_table=table)
        # The others can be graded. The open one is never let through.
        self.assertEqual(graded(named("other-one", [EXIT]), truth="other-one", with_table=table).outcome, "right")
        for truth in ("other-one", "none"):
            self.assertEqual(graded(named(), truth=truth, with_table=table).step, ENOUGH)
        self.assertEqual(table.possible(recording()), {"other-one"})

    def test_08_lines_that_cannot_be_read(self):
        for line, why in {
            "disk what=done say what": "needs a source", "process": "at least one field", "no process": "at least one field", "process exit say exit": "not a field and a value",
            "process exit=137": "has to be said", "process exit=137 say": "one list of fields", "process exit=137 say exit kind": "one list of fields",
            "process exit=137 say kind": "has to be said", "process exit=gone say exit": "not a whole number", "process colour=$c say colour": "has no colour",
            "process exit=137 exit=1 say exit": "not a field and a value", "no process exit=137 say exit": "belong to an entry", "then no process exit=137": "belong to an entry", "no process exit=1|2": "belong to an entry", "2+ process exit=1|2": "belong to an entry", "process exit=1|gone say exit": "not a whole number",
            "1+ process exit=137": "needs a source", "2+ process exit=137 say exit": "belong to an entry", "then": "needs a source", "no": "needs a source", "2+": "needs a source",
        }.items():
            # Below a line that is right, so that nothing else is wrong.
            self.broken(WORKER + f"  process exit=0 say exit\n  {line}\n", why)

    def test_08_lines_that_do_not_go_together(self):
        self.broken(WORKER + "  no log what=done\n", "only on what is not there")
        self.broken(WORKER + "  process exit=137 say exit\n  no log event=$e\n", r"\$e has to stand in an entry first")
        self.broken(WORKER + "  process exit=137 say exit\n  2+ log event=$e\n", r"\$e has to stand in an entry first")
        self.broken(WORKER + "  process process=$x say process\n  no log event=$x\n", "two kinds of things")
        self.broken(WORKER + "  then process exit=137 say exit\n", "then needs a line before")
        self.broken(WORKER + "  never\n  process exit=137 say exit\n", "never stands alone")
        self.broken(WORKER + "  process exit=137 say exit\n  never\n", "never stands alone")
        self.broken("  process exit=137 say exit\n", "a line without a cause")

    def test_08_causes_that_cannot_be_read(self):
        for text in ("Ended: x\n", "ended-after\n", "ended-after:\n", "none: x\n", WORKER + WORKER, "a: too short\n"):
            self.broken(text, "a cause is a code of its own and a sentence")
