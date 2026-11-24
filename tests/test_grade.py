"""Rows 10 to 14 and 16 of docs/contract.md: what comes of a run."""

import unittest

from grader import Broken
from grader.gate import ENOUGH, EXISTS
from grader.grade import DONT_KNOW, Case, read_case
from grader.recording import fingerprint
from tests import world
from tests.world import CALLS, EXIT, NOT_ENOUGH, NOT_IN_DATA, call, claim, graded, named, says, search, valued

# Lets a worker that ended pass for anything.
WEAK = world.TABLE + "weak-cause: Anything at all.\n  process exit=137 say exit\n"
ORDERS = search("Q-orders", "row", "R-ordera", "R-orderb", table="orders")
COUNT = claim("count", "row", "Q-orders", value="2", table="orders")


def question(data, truth, calls=(ORDERS,)):
    return graded(data, calls, truth=truth, kind="question")


class Outcomes(unittest.TestCase):
    def test_10_the_right_cause(self):
        found = graded(named(runbook="send-it-again"))
        self.assertEqual((found.outcome, found.bare, found.step), ("right", "right", ""))
        self.assertEqual(found.decision, ("cause", "ended-after", "none", "send-it-again"))

    def test_10_a_wrong_cause_that_passes_everything(self):
        for truth in ("ended-after", "none"):
            found = graded(named("weak-cause", [EXIT]), truth=truth, with_table=world.table(WEAK))
            self.assertEqual((found.outcome, found.bare), ("false", "false"))

    def test_10_a_wrong_cause_that_only_the_table_stops(self):
        found = graded(named("counted-twice"))
        self.assertEqual((found.outcome, found.bare, found.step, found.decision), ("caught", "false", ENOUGH, DONT_KNOW))

    def test_10_the_right_cause_without_enough_is_not_right(self):
        found = graded(named(claims=[EXIT]))
        self.assertEqual((found.outcome, found.bare, found.step, found.decision), ("caught", "right", ENOUGH, DONT_KNOW))

    def test_10_a_value(self):
        self.assertEqual(question(valued("2", COUNT), "2").outcome, "right")
        # What it says is true, and it is not what was asked.
        self.assertEqual(question(valued("2", COUNT), "3").outcome, "false")
        self.assertEqual(question(valued("2", COUNT), "none").outcome, "false")

    def test_11_rightly_not_known(self):
        found = graded(NOT_ENOUGH, truth="none")
        self.assertEqual((found.outcome, found.decision), ("right", DONT_KNOW))
        self.assertEqual(question(NOT_IN_DATA, "none").outcome, "right")

    def test_12_not_known_although_it_could_be(self):
        self.assertEqual(graded(NOT_ENOUGH).outcome, "gave_up")
        self.assertEqual(question(NOT_IN_DATA, "2").outcome, "gave_up")

    def test_13_caught_where_nothing_can_be_known_is_not_right(self):
        for data, step in ((named("key-was-made-up"), ENOUGH), (named(claims=[says("process", "P-notone", "exit", "137")]), EXISTS)):
            found = graded(data, truth="none")
            self.assertEqual((found.outcome, found.step, found.decision), ("caught", step, DONT_KNOW))
        # The gate alone would have let the first one out.
        self.assertEqual(graded(named("key-was-made-up"), truth="none").bare, "false")

    def test_13_what_the_gate_caught_is_caught_with_and_without_the_table(self):
        self.assertEqual(graded(named(claims=[says("process", "P-notone", "exit", "137")])).bare, "caught")

    def test_14_what_is_no_answer(self):
        for reason, outcome in (("refusal", "refused"), ("max_tokens", "cut_off"), ("model_context_window_exceeded", "cut_off"), ("tool_use", "ran_out")):
            # Even if it looks like a right answer.
            for data in (named(), NOT_ENOUGH, ""):
                for truth in ("ended-after", "none"):
                    found = graded(data, truth=truth, stop_reason=reason)
                    self.assertEqual((found.outcome, found.bare, found.decision), (outcome, outcome, DONT_KNOW))

    def test_14_what_a_limit_stopped(self):
        self.assertEqual(graded(named(), stopped=True).outcome, "stopped")
        self.assertEqual(graded("", stopped=True, stop_reason="", models_said=[]).outcome, "stopped")

    def test_16_a_try_to_act(self):
        found = graded(named(), [*CALLS, call("delete_order", error=True), call("restart", error=True)])
        # It is counted, and the result of the case stays.
        self.assertEqual((found.acts, found.outcome), (("delete_order", "restart"), "right"))
        self.assertEqual(graded(named()).acts, ())

    def test_16_also_if_no_answer_came(self):
        self.assertEqual(graded("", [call("restart", error=True)], stop_reason="refusal").acts, ("restart",))

    def test_10_what_the_model_said_is_kept(self):
        caught = graded(named("counted-twice"))
        self.assertIsNotNone(caught.answer)
        self.assertEqual(caught.answer.cause, "counted-twice")
        self.assertIsNone(graded("no idea").answer)
        self.assertEqual((graded(named()).cost, graded(named()).model, graded(named(), number=3).run), (1500, world.MODEL, 3))


class Truth(unittest.TestCase):
    def test_15_a_run_of_another_case(self):
        with self.assertRaisesRegex(Broken, "a run of c2 for c1"):
            world.grade(Case("c1", "failure", "none"), world.run(named(), case="c2"), world.recording(), world.table(), ())

    def test_15_a_cause_that_is_not_in_the_table(self):
        with self.assertRaisesRegex(Broken, "not in the table"):
            graded(named(), truth="boiled-dry")

    def test_20_a_truth_that_has_changed(self):
        content = b'{"kind": "failure", "truth": "ended-after"}'
        self.assertEqual(read_case("c1", content, fingerprint(content)), Case("c1", "failure", "ended-after"))
        with self.assertRaisesRegex(Broken, "the truth has changed"):
            read_case("c1", content.replace(b"after", b"befor"), fingerprint(content))

    def test_20_a_truth_that_cannot_be_read(self):
        for content in (b'{"kind": "failure"}', b'{"kind": "riddle", "truth": "x"}', b'{"kind": "failure", "truth": 3}', b"[]", b"\xff"):
            with self.subTest(content=content), self.assertRaises(Broken):
                read_case("c1", content, fingerprint(content))

    def test_11_knowable(self):
        self.assertTrue(Case("c1", "question", "0").knowable)
        self.assertFalse(Case("c1", "question", "none").knowable)
