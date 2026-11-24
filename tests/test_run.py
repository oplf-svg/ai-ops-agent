"""Rows 15 and 16 of docs/contract.md: a harness that is wrong is never a miss of the model."""

import json
import unittest

from grader import Broken
from grader.run import TOOLS, read_run
from tests import world
from tests.world import CALLS, call, named, recording, run, run_text, search


class Harness(unittest.TestCase):
    def broken(self, why, calls=CALLS, **changes):
        with self.subTest(why=why, changes=changes), self.assertRaisesRegex(Broken, why):
            run(named(), calls, **changes)

    def test_15_a_run_that_is_right(self):
        found = run(named(), number=2, sent=["one", "two"])
        self.assertEqual((found.case, found.number, found.model, found.apart, found.cost), ("c1", 2, world.MODEL, "", 1500))
        self.assertEqual(found.shown, {"P-worker", "P-theapi", "P-nextwo", "R-inboxa"})
        self.assertEqual(list(found.searches), ["Q-nodone"])
        self.assertEqual(found.sent, ("one", "two"))

    def test_15_another_model_replied(self):
        self.broken("another model replied", models_said=["another-model"])
        self.broken("another model replied", models_said=[world.MODEL, world.MODEL, world.MODEL + "-2"])
        self.broken("nobody replied", models_said=[])

    def test_15_a_tool_showed_what_is_not_there(self):
        self.broken("not in the recording", [call("get_row", "R-notone")])
        self.broken("not in the recording", [call("get_row", 7)])

    def test_15_a_tool_that_does_not_exist_has_answered(self):
        self.broken("has answered", [call("delete_order")])

    def test_15_an_end_that_nobody_knows(self):
        self.broken("not known: pause_turn", stop_reason="pause_turn")
        self.broken("not known", stop_reason="")

    def test_15_searches(self):
        self.broken("id of its own", [search("Q-nodone", "log", what="done"), search("Q-nodone", "log", what="failed")])
        self.broken("id of its own", [search("L-nodone", "log", what="done")])
        self.broken("id of its own", [search("Q-nodon", "log", what="done")])
        self.broken("in no source", [search("Q-nodone", "disk", what="done")])
        self.broken("cannot be read", [search("Q-nodone", "log", what="melted")])
        self.broken("cannot be read", [search("Q-nodone", "log")])
        self.broken("a search", [call("search", search="Q-nodone")])

    def test_15_names_and_types(self):
        good = json.loads(run_text(named()))
        for name in good:
            less = {key: value for key, value in good.items() if key != name}
            with self.subTest(name=name), self.assertRaises(Broken):
                read_run(json.dumps(less), recording())
            with self.subTest(name=name), self.assertRaises(Broken):
                read_run(json.dumps(good | {name: None}), recording())
        for changes in ({"more": 1}, {"run": 0}, {"run": True}, {"cost": -1}, {"cost": 1.5}, {"calls": [{}]}, {"calls": ["x"]}, {"sent": [3]}, {"stopped": 1}):
            with self.subTest(changes=changes), self.assertRaises(Broken):
                read_run(json.dumps(good | changes), recording())

    def test_15_text_that_is_not_a_run(self):
        for text in ("", "[]", "null", "{", '{"run": 1, "run": 2}'):
            with self.subTest(text=text), self.assertRaises(Broken):
                read_run(text, recording())

    def test_16_there_are_five_tools_and_none_of_them_changes_anything(self):
        self.assertEqual(TOOLS, ("search", "get_history", "get_row", "get_series", "list_processes"))

    def test_16_what_an_error_says_does_not_count(self):
        # Also if it says something that is not in the recording.
        found = run(named(), [call("get_row", "R-inboxa", error=True), call("get_row", "R-notone", error=True), search("Q-nodone", "log", error=True)])
        self.assertEqual((found.shown, found.searches), (frozenset(), {}))
