"""Row 1 and 17 of docs/contract.md: what is an answer at all."""

import json
import unittest
import unittest.mock

from grader.answer import CLAIMS, LONGEST, Unusable, read_answer, schema
from grader.fields import FIELDS
from tests import world
from tests.world import RUNBOOKS, answer, claim, graded, named, says, valued

CAUSES = world.table().causes


def read(data, kind="failure"):
    return read_answer(data if isinstance(data, str) else json.dumps(data), kind, CAUSES, RUNBOOKS)


class Form(unittest.TestCase):
    def unusable(self, *answers, kind="failure"):
        for data in answers:
            with self.subTest(data=data), self.assertRaises(Unusable):
                read(data, kind)

    def test_01_the_right_form_is_read(self):
        found = read(named(runbook="send-it-again"))
        self.assertEqual((found.verdict, found.cause, found.runbook, len(found.claims), found.known), ("cause", "ended-after", "send-it-again", 3, True))
        self.assertEqual((found.claims[0].value, found.claims[0].written), (137, "137"))
        self.assertFalse(read(world.NOT_ENOUGH).known)
        self.assertEqual(read(valued("2", claim("count", "row", "Q-orders", value="2", table="orders")), "question").value, "2")

    def test_01_no_json(self):
        good = json.dumps(named())
        self.unusable("", "I don't know", f"Here it is: {good}", good + good, good[:-1], "[" * LONGEST, "null", "[]")

    def test_01_a_text_that_is_too_deep(self):
        # How deep a text may be differs from one version of Python to the next.
        with unittest.mock.patch("grader.strict.json.loads", side_effect=RecursionError):
            self.unusable(json.dumps(named()))

    def test_01_a_number_that_is_not_whole(self):
        with self.assertRaisesRegex(Unusable, "not a whole number"):
            read('{"verdict": NaN}')
        with self.assertRaisesRegex(Unusable, "not a whole number"):
            read('{"verdict": 1.5}')

    def test_01_a_name_twice(self):
        with self.assertRaisesRegex(Unusable, "stands twice"):
            read(json.dumps(world.NOT_ENOUGH)[:-1] + ', "verdict": "not_enough"}')

    def test_01_a_name_too_many_or_too_few(self):
        more, less = named() | {"note": "x"}, named()
        del less["runbook"]
        self.unusable(more, less)
        self.unusable(named(claims=[world.EXIT | {"note": "x"}]), named(claims=[{name: text for name, text in world.EXIT.items() if name != "field"}]))

    def test_01_another_type(self):
        self.unusable(named() | {"cause": None}, named() | {"claims": {}}, named() | {"claims": ["x"]}, named(claims=[world.EXIT | {"value": 137}]), named(claims=[world.SILENT | {"where": "x"}]))

    def test_01_longer_than_allowed(self):
        self.unusable(json.dumps(named()) + " " * LONGEST)
        self.unusable(named(claims=[world.EXIT] * (CLAIMS + 1)), named(claims=[world.EXIT | {"evidence": "x" * 81}]))
        self.assertEqual(len(read(named(claims=[world.EXIT] * CLAIMS)).claims), CLAIMS)

    def test_01_a_word_that_is_not_in_its_list(self):
        self.unusable(named("boiled-dry"), answer("maybe"), named(runbook="delete-it"), named(claims=[says("disk", "P-worker", "exit", "137")]), named(claims=[world.EXIT | {"kind": "because"}]))

    def test_01_the_verdict_of_the_other_kind(self):
        self.unusable(world.NOT_IN_DATA, valued("2", world.EXIT))
        self.unusable(world.NOT_ENOUGH, named(), kind="question")

    def test_01_the_verdict_and_the_rest_disagree(self):
        self.unusable(answer("not_enough", cause="ended-after"), answer("cause", world.EXIT), answer("not_enough", value="3"), named() | {"value": "3"})
        self.unusable(answer("answer", world.EXIT), answer("not_in_data", value="3"), kind="question")

    def test_01_nothing_to_show_for_it(self):
        self.unusable(named(claims=[]))
        self.unusable(valued("3"), kind="question")

    def test_01_a_claim_that_cannot_be_read(self):
        for wrong in ("0137", " 137", "137.0", "-1", "yes", "", "137\n", "\u0661\u0663\u0667", "1" * 13):
            self.unusable(named(claims=[says("process", "P-worker", "exit", wrong)]))
        self.unusable(
            named(claims=[says("process", "P-worker", "colour", "137")]), named(claims=[says("process", "P-worker", "none", "none")]),
            named(claims=[says("row", "R-inboxa", "state", "DONE ")]), named(claims=[says("row", "R-inboxa", "text", "true")]))

    def test_01_conditions(self):
        many = claim("none", "row", "Q-nodone", table="inbox", event="e1", state="done", attempts="1")
        none = claim("none", "row", "Q-nodone")
        twice = world.SILENT | {"where": [{"field": "what", "value": "done"}, {"field": "What", "value": "failed"}]}
        other = world.SILENT | {"where": [{"field": "what", "value": "done", "or": "failed"}]}
        self.unusable(*(named(claims=[one]) for one in (many, none, twice, other)))

    def test_01_a_claim_with_more_than_its_kind_needs(self):
        self.unusable(
            named(claims=[world.EXIT | {"where": [{"field": "kind", "value": "worker"}]}]), named(claims=[world.SILENT | {"field": "what"}]),
            named(claims=[world.SILENT | {"value": "0"}]), named(claims=[claim("count", "log", "Q-nodone", field="what", value="1", what="done")]))

    def test_01_numbers_have_to_be_numbers(self):
        self.unusable(
            named(claims=[claim("count", "log", "Q-nodone", value="none", what="done")]), named(claims=[claim("sum", "row", "Q-nodone", field="state", value="1", table="inbox")]),
            named(claims=[claim("sum", "row", "Q-nodone", field="cents", value="many", table="inbox")]))

    def test_01_capitals_of_a_word_do_not_matter(self):
        shouted = named(claims=[world.EXIT | {"kind": "Is", "source": "Process", "field": "Exit"}]) | {"verdict": "Cause", "cause": "Ended-After"}
        self.assertEqual(read(shouted), read(named(claims=[world.EXIT])))

    def test_01_what_is_no_answer_is_broken_and_not_i_dont_know(self):
        for text in ("", "no idea", "{}"):
            self.assertEqual(graded(text, truth="none").outcome, "broken")

    def test_17_a_runbook_only_with_a_cause(self):
        self.unusable(answer("not_enough", runbook="send-it-again"))
        self.unusable(answer("not_in_data", runbook="send-it-again"), kind="question")


class Schema(unittest.TestCase):
    def test_01_the_schema_is_closed_and_uses_only_what_the_service_knows(self):
        def walk(node):
            self.assertLessEqual(node.keys(), {"type", "properties", "required", "additionalProperties", "items", "enum"})
            if node["type"] == "object":
                self.assertIs(node["additionalProperties"], False)
                self.assertEqual(node["required"], list(node["properties"]))
                for inner in node["properties"].values():
                    walk(inner)
            if node["type"] == "array":
                walk(node["items"])

        for kind in ("failure", "question"):
            walk(schema(kind, CAUSES, RUNBOOKS))

    def test_01_the_schema_has_the_names_and_words_of_the_form(self):
        found = schema("failure", CAUSES, RUNBOOKS)["properties"]
        self.assertEqual(list(found), list(named()))
        self.assertEqual(list(found["claims"]["items"]["properties"]), list(world.EXIT))
        self.assertEqual(found["cause"]["enum"], [*CAUSES, "none"])
        self.assertEqual(set(found["claims"]["items"]["properties"]["source"]["enum"]), set(FIELDS))
        self.assertEqual(schema("question", CAUSES, RUNBOOKS)["properties"]["cause"]["enum"], ["none"])
        self.assertEqual(schema("question", CAUSES, RUNBOOKS)["properties"]["runbook"]["enum"], ["none"])
