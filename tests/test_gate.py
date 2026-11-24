"""Rows 2 to 7 of docs/contract.md: whether what an answer relies on exists, was seen and is true."""

import unittest

from grader.gate import EXISTS, SEEN, TRUE, VALUE, Caught, check
from grader.answer import read_answer
from tests import world
from tests.world import CALLS, ENDED, RUNBOOKS, answer, call, claim, graded, named, recording, says, search, valued

ORDERS = search("Q-orders", "row", "R-ordera", "R-orderb", table="orders")
COUNT = claim("count", "row", "Q-orders", value="2", table="orders")
SUM = claim("sum", "row", "Q-orders", field="cents", value="1200", table="orders")


def step(data, calls=CALLS, **more):
    """At which step an answer is caught. Empty if it passes."""
    kind = "question" if data["verdict"] in ("answer", "not_in_data") else "failure"
    return graded(data, calls, kind=kind, **({"truth": "2"} if kind == "question" else {}) | more).step


class Exists(unittest.TestCase):
    def test_02_an_id_that_does_not_exist(self):
        self.assertEqual(step(named(claims=[world.EXIT, says("row", "R-notone", "state", "done"), world.SILENT])), EXISTS)

    def test_02_an_id_that_is_nearly_right(self):
        for id in ("P-worke", "P-workerx", "p-worker", "P-WORKER", "L-worker", ""):
            self.assertEqual(step(named(claims=[says("process", id, "exit", "137")])), EXISTS, id)

    def test_02_a_search_that_nobody_made(self):
        self.assertEqual(step(named(claims=[world.EXIT, world.DONE, world.SILENT | {"evidence": "Q-nothin"}])), EXISTS)

    def test_02_an_entry_is_no_search_and_a_search_is_no_entry(self):
        self.assertEqual(step(named(claims=[world.SILENT | {"evidence": "P-worker"}])), EXISTS)
        self.assertEqual(step(named(claims=[says("log", "Q-nodone", "what", "done")])), EXISTS)

    def test_02_comes_before_everything_else(self):
        # One claim is not true, one was not seen, and one does not exist: the worst is named.
        claims = [says("process", "P-worker", "exit", "0"), says("row", "R-totals", "orders", "2"), says("row", "R-notone", "state", "done")]
        self.assertEqual(step(named(claims=claims)), EXISTS)
        self.assertEqual(step(named(claims=claims[:2])), SEEN)


class Seen(unittest.TestCase):
    def test_03_an_id_that_no_tool_showed(self):
        # Everything in this answer is right and enough. But nobody looked at the row.
        self.assertEqual(step(named(), (CALLS[0], CALLS[2])), SEEN)

    def test_03_an_id_that_only_an_error_showed(self):
        calls = [call("list_processes", "P-worker", error=True), *CALLS[1:]]
        self.assertEqual(step(named(), calls), SEEN)

    def test_05_another_search(self):
        for other in (search("Q-nodone", "log", what="done", event="e2"), search("Q-nodone", "log", what="done"), search("Q-nodone", "log", what="failed", event="e1"), search("Q-nodone", "row", event="e1")):
            self.assertEqual(step(named(), [*CALLS[:2], other]), SEEN)
        elsewhere = search("Q-noshop", "front", feed="south-web", event="e9")
        self.assertEqual(step(answer("not_enough", claim("none", "log", "Q-noshop", feed="south-web", event="e9")), [elsewhere]), SEEN)

    def test_05_the_order_of_the_conditions_does_not_matter(self):
        self.assertEqual(step(named(), [*CALLS[:2], search("Q-nodone", "log", event="e1", what="done")]), "")

    def test_05_a_search_in_a_part_of_the_time(self):
        for part in ({"since": "100"}, {"until": "300"}, {"since": "0", "until": "0"}):
            self.assertEqual(step(named(), [*CALLS[:2], search("Q-nodone", "log", what="done", event="e1", **part)]), SEEN)

    def test_05_a_search_that_was_an_error(self):
        self.assertEqual(step(named(), [*CALLS[:2], search("Q-nodone", "log", what="done", event="e1", error=True)]), EXISTS)


class True_(unittest.TestCase):
    def test_04_a_field_that_says_something_else(self):
        for wrong in (says("process", "P-worker", "exit", "0"), says("process", "P-worker", "exit", "none"), says("process", "P-worker", "kind", "api")):
            self.assertEqual(step(named(claims=[wrong, world.DONE, world.SILENT])), TRUE)

    def test_04_a_field_of_another_source(self):
        # The entry is a process. It has an event as little as a log line has an exit.
        self.assertEqual(step(named(claims=[*world.RIGHT, says("log", "P-worker", "process", "p2")])), TRUE)

    def test_04_empty_is_none_and_nothing_else(self):
        self.assertEqual(step(answer("not_enough", says("process", "P-nextwo", "exit", "none"))), "")
        self.assertEqual(step(answer("not_enough", says("process", "P-nextwo", "exit", "0"))), TRUE)

    def test_04_one_claim_that_is_not_true_is_enough(self):
        wrong = says("process", "P-theapi", "exit", "137")
        self.assertEqual(step(named(claims=[*world.RIGHT, wrong])), TRUE)
        self.assertEqual(step(named(claims=[wrong, *world.RIGHT])), TRUE)

    def test_04_also_in_an_answer_that_says_not_enough(self):
        found = graded(answer("not_enough", says("process", "P-worker", "exit", "0")), truth="none")
        self.assertEqual((found.outcome, found.step), ("caught", TRUE))

    def test_04_a_count(self):
        self.assertEqual(step(valued("2", COUNT), [ORDERS]), "")
        for wrong in ("1", "3", "0"):
            self.assertEqual(step(valued(wrong, COUNT | {"value": wrong}), [ORDERS]), TRUE)

    def test_04_a_count_is_about_all_and_not_about_what_was_shown(self):
        part = search("Q-orders", "row", "R-ordera", table="orders")
        self.assertEqual(step(valued("1", COUNT | {"value": "1"}), [part]), TRUE)
        self.assertEqual(step(valued("2", COUNT), [part]), "")

    def test_04_all_conditions_have_to_hold(self):
        both = search("Q-orders", "row", table="orders", event="e1")
        self.assertEqual(step(valued("1", claim("count", "row", "Q-orders", value="1", table="orders", event="e1")), [both], truth="1"), "")
        self.assertEqual(step(valued("3", claim("count", "row", "Q-orders", value="3", table="orders", event="e1")), [both]), TRUE)

    def test_04_a_sum(self):
        self.assertEqual(step(valued("1200", SUM), [ORDERS], truth="1200"), "")
        for wrong in ("500", "700", "2", "1201"):
            self.assertEqual(step(valued(wrong, SUM | {"value": wrong}), [ORDERS]), TRUE)

    def test_04_a_sum_of_what_is_not_there(self):
        self.assertEqual(step(valued("0", SUM | {"value": "0", "field": "attempts"}), [ORDERS]), TRUE)
        nothing = search("Q-orders", "row", table="conflicts")
        self.assertEqual(step(valued("0", claim("sum", "row", "Q-orders", field="cents", value="0", table="conflicts")), [nothing]), TRUE)

    def test_04_an_absence(self):
        there = [*CALLS[:2], search("Q-nodone", "log", what="done", event="e2")]
        self.assertEqual(step(answer("not_enough", world.SILENT)), "")
        # It was looked for and found, but not shown.
        self.assertEqual(step(answer("not_enough", claim("none", "log", "Q-nodone", what="done", event="e2")), there), TRUE)

    def test_06_a_source_that_was_not_recorded_all_the_time(self):
        gap = recording(*ENDED, missing=[("log", 0, 50)])
        self.assertEqual(step(answer("not_enough", world.SILENT), in_recording=gap), TRUE)
        self.assertEqual(step(valued("2", claim("count", "log", "Q-stored", value="2", what="stored")), [search("Q-stored", "log", what="stored")], in_recording=gap), TRUE)
        self.assertEqual(step(valued("1", claim("sum", "log", "Q-stored", field="attempt", value="1", what="done")), [search("Q-stored", "log", what="done")], in_recording=gap), TRUE)

    def test_06_a_gap_elsewhere_does_not_matter_and_what_was_shown_is_there(self):
        self.assertEqual(step(answer("not_enough", world.SILENT), in_recording=recording(*ENDED, missing=[("series", 0, 50)])), "")
        self.assertEqual(step(answer("not_enough", world.EXIT), in_recording=recording(*ENDED, missing=[("process", 0, 50)])), "")


class Value(unittest.TestCase):
    def test_07_a_value_that_no_claim_has(self):
        self.assertEqual(step(valued("3", COUNT), [ORDERS]), VALUE)
        self.assertEqual(step(valued("north", COUNT), [ORDERS]), VALUE)

    def test_07_one_of_several_claims_is_enough(self):
        self.assertEqual(step(valued("1200", COUNT, SUM), [ORDERS], truth="1200"), "")

    def test_07_none_is_not_a_value(self):
        absent = search("Q-absent", "row", table="conflicts")
        self.assertEqual(step(valued("2", claim("none", "row", "Q-absent", table="conflicts")), [absent]), VALUE)


class Everything(unittest.TestCase):
    def test_04_what_is_right_passes(self):
        seen = recording()
        check(read_answer(world.json.dumps(named()), "failure", world.table().causes, RUNBOOKS), world.run(named()), seen)

    def test_04_being_caught_says_where_and_why(self):
        with self.assertRaisesRegex(Caught, "not true: P-worker: exit is not 0"):
            wrong = named(claims=[says("process", "P-worker", "exit", "0")])
            check(read_answer(world.json.dumps(wrong), "failure", world.table().causes, RUNBOOKS), world.run(wrong), recording())
