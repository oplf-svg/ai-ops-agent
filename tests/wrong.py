"""Proves that the tests can fail: puts one mistake at a time into a copy, and looks whether the tests notice it.

Each mistake names the test that has to notice it. Every one of these mistakes is easy to make. A test that only breaks, because
the changed code does not run at all, has noticed nothing. And the other way round: each test is named by some mistake, because a
test that nothing can make fail proves nothing.

    python -m tests.wrong            all of them
    python -m tests.wrong 2/4        the second of four parts
    python -m tests.wrong NAME...    only these
"""

import collections
import concurrent.futures
import dataclasses
import json
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Runs all tests and says which of them looked and saw something wrong, and which did not get as far as that.
RUN = """
import json, sys, unittest

# The changed code does not run. Whatever else is raised is what the grader does with what the test gave it.
NOT_EVEN_CODE = (NameError, ImportError, SyntaxError, AttributeError, TypeError)


class Found(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.failed, self.broken = set(), {}

    def note(self, test, error):
        id = getattr(test, "test_case", test).id()
        if issubclass(error[0], NOT_EVEN_CODE):
            self.broken[id] = repr(error[1])[:200]
        else:
            self.failed.add(id)

    def addFailure(self, test, error):
        self.note(test, error)

    addError = addFailure

    def addSubTest(self, test, subtest, error):
        if error:
            self.note(subtest, error)


found = Found()
unittest.defaultTestLoader.discover("tests", top_level_dir=".").run(found)
print(json.dumps({"run": found.testsRun, "failed": sorted(found.failed), "broken": found.broken}))
"""


@dataclasses.dataclass(frozen=True)
class Wrong:
    """One mistake: what it is, where it goes, and the test that has to notice it."""

    name: str
    what: str
    file: str
    noticed_by: str
    changes: tuple

    def put_into(self, text):
        for old, new in self.changes:
            if text.count(old) != 1:
                raise ValueError(f"stands {text.count(old)} times in {self.file}: {old}")
            text = text.replace(old, new)
        return text


def mistakes():
    found = []

    def of(file, folder="grader", end=".py"):
        def change(name, what, noticed_by, *changes):
            found.append(Wrong(name, what, f"{folder}/{file}{end}", noticed_by, changes))
        return change

    wrong = of("fields")
    fits = "return isinstance(value, str) and value != NONE and self._form.fullmatch(value) is not None"
    wrong("fields.any_text", "Any text can stand in a recording", "test_21_free_text_cannot_get_in", (fits, "return isinstance(value, str) and value != NONE"))
    wrong("fields.only_the_start", "Only the start of a text has to be right", "test_21_every_word_is_from_a_list_or_of_a_fixed_form", ("self._form.fullmatch(value)", "self._form.match(value)"))
    wrong("fields.none_is_a_name", "A shop can have the name none", "test_21_every_word_is_from_a_list_or_of_a_fixed_form", (fits, "return isinstance(value, str) and self._form.fullmatch(value) is not None"))
    wrong("fields.true_is_1", "Yes counts as 1", "test_04_reading_a_value", ("return type(value) is int and 0 <= value < MOST", "return isinstance(value, int) and 0 <= value < MOST"))
    wrong("fields.below_0", "A number can be below 0", "test_21_types", ("return type(value) is int and 0 <= value < MOST", "return type(value) is int and value < MOST"))
    wrong("fields.any_size", "A number can have any size", "test_21_types", ("return type(value) is int and 0 <= value < MOST", "return type(value) is int and 0 <= value"))
    wrong("fields.numbers_as_they_come", "A number can be written in several ways", "test_01_a_claim_that_cannot_be_read", ('if not re.fullmatch(r"0|[1-9][0-9]{0,11}", written):', "if not written.strip().isdigit():"))
    wrong("fields.everything_else_is_no", "Whatever is not yes is no", "test_04_reading_a_value", ('if written not in ("yes", "no"):', "if not written:"))
    wrong("fields.yes_as_a_text", "Yes can stand in a recording as a text", "test_21_types", ("return type(value) is bool", 'return type(value) is bool or value in ("yes", "no")'))
    wrong("fields.short_ids", "An id can be short enough to be guessed", "test_21_ids", ("[a-z2-7]{{6}}", "[a-z2-7]{{4,6}}"))
    wrong("fields.ids_of_any_source", "A row can have the id of a log line", "test_21_ids", (" and text[0] == letter", ""))
    wrong("fields.many_conditions", "A claim can have any number of conditions", "test_01_conditions", ("not 1 <= len(where) <= CONDITIONS", "not 1 <= len(where)"))
    wrong("fields.no_conditions", "A claim needs no condition", "test_01_conditions", ("not 1 <= len(where) <= CONDITIONS", "len(where) > CONDITIONS"))
    wrong("fields.condition_twice", "Of two conditions for one field, the last one counts", "test_01_conditions", ("if field in found:", "if False:"))
    wrong("fields.more_in_a_condition", "A condition can say more than a field and a value", "test_01_conditions", ('set(one) != {"field", "value"}', 'not {"field", "value"} <= set(one)'))
    wrong("fields.none_is_a_value", "Nobody can say that a field is empty", "test_04_a_field_that_says_something_else", ("return None if written == NONE else kind.read(written)", "return kind.read(written)"))

    wrong = of("strict")
    wrong("strict.the_last_counts", "Of a name that stands twice, the last one counts", "test_01_a_name_twice", ("if len(found) != len(pairs):", "if False:"))
    wrong("strict.any_number", "A number can be anything that Python takes for one", "test_01_a_number_that_is_not_whole", (", parse_float=_no, parse_constant=_no", ""))
    wrong("strict.any_length", "A text can have any length", "test_01_longer_than_allowed", ("if len(text) > most:", "if False:"))
    wrong("strict.too_deep", "Brackets in brackets end the grader", "test_01_a_text_that_is_too_deep", ("except RecursionError:", "except ZeroDivisionError:"))

    wrong = of("recording")
    wrong("recording.same_id", "Two entries can have the same id", "test_20_order_and_ids_of_a_whole_recording", ("if len(self.by_id) != len(self.entries):", "if False:"))
    wrong("recording.any_order", "The entries can be in any order", "test_20_order_and_ids_of_a_whole_recording", ("if any(one.at > other.at for", "if False and any(one.at > other.at for"))
    wrong("recording.raw_of_nobody", "A raw line needs no entry", "test_20_what_is_not_a_raw_line", ("if not self.raw.keys() <= self.by_id.keys():", "if False:"))
    wrong("recording.any_condition", "One condition of several is enough", "test_04_matching_takes_all_conditions", ("return all(self.values.get(field) == value", "return any(self.values.get(field) == value"))
    wrong("recording.every_source", "A search finds entries of other sources", "test_04_matching_takes_all_conditions", ("if entry.source == source and entry.fits(conditions)", "if entry.fits(conditions)"))
    wrong("recording.no_gaps", "Nobody looks whether a source was recorded all the time", "test_06_a_source_that_was_not_recorded_all_the_time", ("return any(gap_source == source for gap_source, _, _ in self.missing)", "return False"))
    wrong("recording.gaps_everywhere", "A gap in one source spoils all the others", "test_06_a_gap_elsewhere_does_not_matter_and_what_was_shown_is_there", ("return any(gap_source == source for gap_source, _, _ in self.missing)", "return bool(self.missing)"))
    unknown = "if field not in FIELDS[source] or not FIELDS[source][field].fits(value):"
    wrong("recording.unknown_fields", "An entry can have fields that nobody knows", "test_21_free_text_cannot_get_in", (unknown, "if field in FIELDS[source] and not FIELDS[source][field].fits(value):"))
    wrong("recording.unknown_values", "A known field can have any value", "test_21_free_text_cannot_get_in", (unknown, "if field not in FIELDS[source]:"))
    wrong("recording.any_id", "An entry can have any id", "test_21_ids", ("if not is_id(id, LETTER[source]):", "if not isinstance(id, str):"))
    wrong("recording.any_time", "A time can be anything", "test_21_types", ("if not NUMBER.fits(at):", "if at is None:"))
    wrong("recording.any_source", "An entry of an unknown source is taken for a log line", "test_21_types", ("    if not isinstance(source, str) or source not in FIELDS:\n", '    source = source if isinstance(source, str) and source in FIELDS else "log"\n    if not source:\n'))
    wrong("recording.meta_not_checked", "Whoever changes a recording can write new fingerprints", "test_20_other_files_with_their_own_fingerprints", ("if fingerprint(meta) != expected:", "if False:"))
    wrong("recording.files_not_checked", "A file can change", "test_20_a_file_that_has_changed", ('if fingerprint(content[name]) != meta["files"][name]:', "if False:"))
    wrong("recording.more_files", "The truth can lie beside the recording", "test_20_a_file_too_many_or_too_few", ('if {path.name for path in folder.iterdir()} != {"meta.json", *FILES}:', 'if not {"meta.json", *FILES} <= {path.name for path in folder.iterdir()}:'))
    wrong("recording.other_line_ends", "A character inside a text ends the line", "test_20_a_recording_that_is_right", ('.removesuffix("\\n").split("\\n")', ".splitlines()"))
    wrong("recording.more_in_meta", "The truth can stand in meta.json", "test_20_meta_that_is_not_complete", ("set(meta) != META", "not META <= set(meta)"))
    wrong("recording.fewer_fingerprints", "A file needs no fingerprint", "test_20_meta_that_is_not_complete", (' or set(meta["files"]) != set(FILES)', ""))
    wrong("recording.gap_backwards", "A gap can end before it starts", "test_20_gaps", (' or data["from"] > data["to"]', ""))
    wrong("recording.gaps_as_they_come", "What is not a list of gaps counts as no gap", "test_20_gaps", ("if not isinstance(missing, list):", "if False:"))
    wrong("recording.raw_of_any_type", "A raw line can be anything", "test_20_what_is_not_a_raw_line", ("all(isinstance(text, str) for text in line.values()) for line in raw", "True for line in raw"))
    wrong("recording.raw_twice", "Of two raw lines with the same id, the last one counts", "test_20_what_is_not_a_raw_line", ('if len({line["id"] for line in raw}) != len(raw):', "if False:"))
    wrong("recording.entry_as_it_comes", "An entry can be read in two ways", "test_21_what_is_not_an_entry", ("data = strict.loads(line, 2_000)", 'data = __import__("json").loads(line)'))

    wrong = of("answer")
    wrong("answer.more_names", "An answer can say more than the form has", "test_01_a_name_too_many_or_too_few", ("set(data) != set(names)", "not set(names) <= set(data)"))
    wrong("answer.long_texts", "A text in an answer can have any length", "test_01_longer_than_allowed", (" or len(value) > SHORT", ""))
    wrong("answer.any_type", "A number is as good as a text", "test_01_another_type", ('        elif not isinstance(value, str) or len(value) > SHORT:\n            raise Unusable(f"{name} is not a short text")\n', "        else:\n            data[name] = str(value)\n"))
    wrong("answer.capitals", "The capitals of a word matter", "test_01_capitals_of_a_word_do_not_matter", ('(data[name].lower() for name in ("kind", "source", "field"))', '(data[name] for name in ("kind", "source", "field"))'))
    wrong("answer.any_verdict", "A failure can be answered like a question", "test_01_the_verdict_of_the_other_kind", ("verdict not in VERDICTS[kind]", "verdict not in sum(VERDICTS.values(), ())"))
    wrong("answer.any_cause", "A cause needs not be in the table", "test_01_a_word_that_is_not_in_its_list", (" or cause not in (*causes, NONE)", ""))
    wrong("answer.any_runbook", "A runbook needs not be in the list", "test_01_a_word_that_is_not_in_its_list", (" or runbook not in (*runbooks, NONE)", ""))
    wrong("answer.any_kind", "A claim of an unknown kind is taken for another one", "test_01_a_word_that_is_not_in_its_list", ("    if kind not in KINDS or source not in FIELDS:\n", '    kind = kind if kind in KINDS else "is"\n    if source not in FIELDS:\n'))
    disagree = 'if (verdict == "cause") != (cause != NONE) or (verdict == "answer") != (data["value"] != NONE):'
    wrong("answer.cause_without_verdict", "It can say not enough and name a cause", "test_01_the_verdict_and_the_rest_disagree", (disagree, 'if (verdict == "cause" and cause == NONE) or (verdict == "answer") != (data["value"] != NONE):'))
    wrong("answer.verdict_without_cause", "It can say that there is a cause and name none", "test_01_the_verdict_and_the_rest_disagree", (disagree, 'if (verdict != "cause" and cause != NONE) or (verdict == "answer") != (data["value"] != NONE):'))
    wrong("answer.value_without_verdict", "It can say not in the data and give a value", "test_01_the_verdict_and_the_rest_disagree", (disagree, 'if (verdict == "cause") != (cause != NONE) or (verdict == "answer" and data["value"] == NONE):'))
    wrong("answer.runbook_alone", "It can propose a runbook without knowing the cause", "test_17_a_runbook_only_with_a_cause", ('if runbook != NONE and verdict != "cause":', "if False:"))
    wrong("answer.many_claims", "It can make any number of claims", "test_01_longer_than_allowed", ('if len(data["claims"]) > CLAIMS:', "if False:"))
    wrong("answer.one_claim_fewer", "It can make one claim fewer than it says", "test_01_longer_than_allowed", ('if len(data["claims"]) > CLAIMS:', 'if len(data["claims"]) >= CLAIMS:'))
    wrong("answer.nothing_to_show", "A cause needs no claim", "test_01_nothing_to_show_for_it", ("if answer.known and not answer.claims:", "if False:"))
    wrong("answer.conditions_of_is", "Conditions that nobody looks at", "test_01_a_claim_with_more_than_its_kind_needs", ('(kind == "is" and conditions) or ', ""))
    wrong("answer.field_of_count", "A field that nobody looks at", "test_01_a_claim_with_more_than_its_kind_needs", ('(kind in ("count", "none") and field != NONE) or ', ""))
    wrong("answer.value_of_none", "A value that nobody looks at", "test_01_a_claim_with_more_than_its_kind_needs", (' or (kind == "none" and data["value"] != NONE)', ""))
    wrong("answer.sum_of_words", "Words can be added up", "test_01_numbers_have_to_be_numbers", ('                read(source, field, "0")\n', ""))
    wrong("answer.count_of_none", "None is a number", "test_01_numbers_have_to_be_numbers", ('            case "count":\n                value = NUMBER.read(data["value"])\n', '            case "count":\n                value = read("front", "status", data["value"])\n'))
    wrong("answer.takes_what_is_around", "Text around the form does not matter", "test_01_no_json", ("strict.loads(text, LONGEST)", 'strict.loads(text[text.find("{"):text.rfind("}") + 1], LONGEST)'))
    wrong("answer.written_is_lost", "What the model wrote is lost", "test_01_the_right_form_is_read", ('value, data["value"], data["evidence"])', 'value, "", data["evidence"])'))
    wrong("answer.broken_is_dont_know", "What cannot be read counts as I don't know", "test_01_what_is_no_answer_is_broken_and_not_i_dont_know", ("        raise Unusable(str(problem)) from None\n    verdict", "        return Answer(VERDICTS[kind][1], NONE, NONE, (), NONE)\n    verdict"))
    wrong("schema.open", "The schema lets other names through", "test_01_the_schema_is_closed_and_uses_only_what_the_service_knows", ('"additionalProperties": False', '"additionalProperties": True'))
    wrong("schema.nothing_required", "The schema needs no name at all", "test_01_the_schema_is_closed_and_uses_only_what_the_service_knows", ('"required": list(properties)', '"required": []'))
    wrong("schema.verdict_first", "The schema asks for the verdict before the claims", "test_01_the_schema_has_the_names_and_words_of_the_form", ("claims=many(claim), verdict=word(VERDICTS[kind]), cause", "verdict=word(VERDICTS[kind]), claims=many(claim), cause"))
    wrong("schema.questions_have_causes", "The schema lets a question be answered with a cause", "test_01_the_schema_has_the_names_and_words_of_the_form", ('cause=word([*causes, NONE] if kind == "failure" else [NONE])', "cause=word([*causes, NONE])"))

    wrong = of("run")
    wrong("run.any_model", "Nobody looks which model replied", "test_15_another_model_replied", ('all(model == data["model_asked"] for model in data["models_said"])', "True"))
    wrong("run.first_model", "Only the first reply has to be from the right model", "test_15_another_model_replied", ('all(model == data["model_asked"] for model in data["models_said"])', 'all(model == data["model_asked"] for model in data["models_said"][:1])'))
    wrong("run.nobody_replied", "A run without a reply can be judged", "test_15_another_model_replied", ('    _need(data["stopped"] or data["models_said"], "nobody replied")\n', ""))
    wrong("run.any_end", "A run can end in any way", "test_15_an_end_that_nobody_knows", ('_need(data["stopped"] or data["stop_reason"] in ENDS,', "_need(True,"))
    wrong("run.refusal_is_an_answer", "A refusal is read like an answer", "test_14_what_is_no_answer", ('"refusal": "refused"', '"refusal": ""'))
    wrong("run.cut_off_is_an_answer", "A cut off answer is read like a whole one", "test_14_what_is_no_answer", ('"max_tokens": "cut_off"', '"max_tokens": ""'))
    wrong("run.ran_out_is_an_answer", "Whoever runs out of calls has answered", "test_14_what_is_no_answer", ('"tool_use": "ran_out"', '"tool_use": ""'))
    wrong("run.stopped_is_an_answer", "What a limit stopped is read like an answer", "test_14_what_a_limit_stopped", ('"stopped" if data["stopped"] else ENDS[data["stop_reason"]]', 'ENDS.get(data["stop_reason"], "")'))
    wrong("run.shows_anything", "A tool can show what is not in the recording", "test_15_a_tool_showed_what_is_not_there", ("_need(isinstance(id, str) and id in recording.by_id,", "_need(True,"))
    wrong("run.errors_show", "What an error says was shown", "test_03_an_id_that_only_an_error_showed", ('if call["error"]:', "if False:"))
    wrong("run.errors_are_checked", "An error that names what is not there ends the grading", "test_16_what_an_error_says_does_not_count", ('if call["error"]:', 'if call["error"] and call["tool"] == "search":'))
    wrong("run.acts_not_counted", "A try to act is not counted", "test_16_a_try_to_act", ('            acts.append(call["tool"])\n', ""))
    wrong("run.acts_of_errors", "A try to act is counted only once", "test_16_a_try_to_act", ('            acts.append(call["tool"])\n', '            acts[:] = [call["tool"]]\n'))
    wrong("run.unknown_tools_answer", "A tool that does not exist can answer", "test_15_a_tool_that_does_not_exist_has_answered", ('            _need(call["error"], "a tool that does not exist has answered")\n', ""))
    wrong("run.one_more_tool", "There is a tool that changes something", "test_16_there_are_five_tools_and_none_of_them_changes_anything", ('"list_processes")', '"list_processes", "restart")'))
    wrong("run.same_search", "Two searches can have the same id", "test_15_searches", (' and call["search"] not in searches', ""))
    wrong("run.any_search_id", "A search can have any id", "test_15_searches", ('is_id(call["search"], SEARCH) and ', ""))
    wrong("run.unreadable_search", "A search that cannot be read asked for nothing", "test_15_searches", ('        raise Broken(f"a run that is not right: a search that was answered and cannot be read: {problem}") from None\n', "        conditions = frozenset()\n"))
    wrong("run.part_is_whole", "A search in a part of the time counts for all of it", "test_05_a_search_in_a_part_of_the_time", ('data["from"] == data["to"] == NONE', "True"))
    wrong("run.half_open_is_whole", "A search with only a start counts for all of the time", "test_05_a_search_in_a_part_of_the_time", ('data["from"] == data["to"] == NONE', 'NONE in (data["from"], data["to"])'))
    wrong("run.more_names", "A run can have more names", "test_15_names_and_types", ("set(data) == RUN", "RUN <= set(data)"))
    wrong("run.any_numbers", "A run can have any number and any cost", "test_15_names_and_types", ('_need(type(data["run"]) is int and data["run"] > 0 and type(data["cost"]) is int and data["cost"] >= 0 and type(data["stopped"]) is bool, "a number")', "pass"))
    wrong("run.as_it_comes", "A run can be read in two ways", "test_15_text_that_is_not_a_run", ("data = strict.loads(text, 20_000_000)", 'data = __import__("json").loads(text) or {}'), ('_need(isinstance(data, dict) and set(data) == RUN, "a name too many or too few")', 'if not isinstance(data, dict) or set(data) != RUN:\n        return None'))
    wrong("run.number", "Every run is the first one", "test_15_a_run_that_is_right", ('data["case"], data["run"], data["model_asked"]', 'data["case"], 1, data["model_asked"]'))

    wrong = of("gate")
    wrong("gate.ids_not_looked_up", "An id needs not exist", "test_02_an_id_that_does_not_exist", ("    if not there:", "    if False:"))
    wrong("gate.searches_not_looked_up", "A search needs not have been made", "test_02_a_search_that_nobody_made", ("there = claim.evidence in (recording.by_id if claim.kind == \"is\" else run.searches)", 'there = claim.kind != "is" or claim.evidence in recording.by_id'))
    wrong("gate.any_id_will_do", "An entry can stand for a search", "test_02_an_entry_is_no_search_and_a_search_is_no_entry", ("there = claim.evidence in (recording.by_id if claim.kind == \"is\" else run.searches)", "there = claim.evidence in recording.by_id or claim.evidence in run.searches"))
    wrong("gate.nearly_the_id", "The capitals of an id do not matter", "test_02_an_id_that_is_nearly_right", ("there = claim.evidence in (recording.by_id if claim.kind == \"is\" else run.searches)", "there = claim.evidence.upper() in {id.upper() for id in (*recording.by_id, *run.searches)}"))
    wrong("gate.errors_made_the_search", "A search that failed counts", "test_05_a_search_that_was_an_error", ("there = claim.evidence in (recording.by_id if claim.kind == \"is\" else run.searches)", 'there = claim.evidence in recording.by_id or claim.kind != "is"'))
    wrong("gate.not_seen", "An id needs not have been shown", "test_03_an_id_that_no_tool_showed", ("if claim.evidence not in run.shown:", "if False:"))
    wrong("gate.other_search", "The search can have had other conditions", "test_05_another_search", ("if search.source != claim.source or search.conditions != claim.conditions:", "if search.source != claim.source:"))
    wrong("gate.other_source", "The search can have been in another source", "test_05_another_search", ("if search.source != claim.source or search.conditions != claim.conditions:", "if search.conditions != claim.conditions:"))
    wrong("gate.wider_search", "The search can have had fewer conditions", "test_05_another_search", ("search.conditions != claim.conditions", "not search.conditions <= claim.conditions"))
    wrong("gate.same_order", "The conditions have to be in the same order", "test_05_the_order_of_the_conditions_does_not_matter", ("search.conditions != claim.conditions", "repr(sorted(search.conditions)) != repr(sorted(claim.conditions, reverse=True))"))
    wrong("gate.part_of_the_time", "The search can have been in a part of the time", "test_05_a_search_in_a_part_of_the_time", ("if not search.whole:", "if False:"))
    wrong("gate.source_of_an_entry", "A process can be called a log line", "test_04_a_field_of_another_source", ("entry.source != claim.source or ", ""))
    wrong("gate.value_of_an_entry", "Whatever is said about an entry is true", "test_04_a_field_that_says_something_else", (" or entry.get(claim.field) != claim.value", ""))
    wrong("gate.empty_is_anything", "An empty field has every value", "test_04_empty_is_none_and_nothing_else", ("entry.get(claim.field) != claim.value", "entry.get(claim.field) not in (None, claim.value)"))
    wrong("gate.gaps", "What was not recorded was not there", "test_06_a_source_that_was_not_recorded_all_the_time", ("if recording.has_gap(claim.source):", "if False:"))
    wrong("gate.gaps_for_what_was_shown", "What was shown does not count if something else is missing", "test_06_a_gap_elsewhere_does_not_matter_and_what_was_shown_is_there", ('    if claim.kind == "is":\n        entry = recording', '    if recording.has_gap(claim.source):\n        raise Caught(TRUE, "a gap")\n    if claim.kind == "is":\n        entry = recording'))
    wrong("gate.count_at_least", "A count can be too small", "test_04_a_count", ("right = len(found) == claim.value", "right = len(found) >= claim.value"))
    wrong("gate.count_at_most", "A count can be too large", "test_04_a_count", ("right = len(found) == claim.value", "right = len(found) <= claim.value"))
    shown = (("def _true(claim, recording):", "def _true(claim, recording, run):"), ("        _true(claim, recording)\n", "        _true(claim, recording, run)\n"),
             ("    found = recording.matching(claim.source, claim.conditions)\n", "    found = [entry for entry in recording.matching(claim.source, claim.conditions) if entry.id in run.shown]\n"))
    wrong("gate.count_of_what_was_shown", "Only what was shown is counted", "test_04_a_count_is_about_all_and_not_about_what_was_shown", *shown)
    wrong("gate.absence_of_what_was_shown", "What was not shown is not there", "test_04_an_absence", *shown)
    wrong("gate.conditions_by_chance", "Only one of the conditions is looked at", "test_04_all_conditions_have_to_hold", ("recording.matching(claim.source, claim.conditions)", "recording.matching(claim.source, sorted(claim.conditions)[-1:])"))
    wrong("gate.sum_counts", "A sum is how many there are", "test_04_a_sum", ("sum(values) == claim.value", "len(values) == claim.value"))
    wrong("gate.sum_of_the_first", "A sum is the first value", "test_04_a_sum", ("sum(values) == claim.value", "values[0] == claim.value"))
    wrong("gate.sum_of_nothing", "Nothing adds up to 0", "test_04_a_sum_of_what_is_not_there", ("bool(values) and ", ""))
    wrong("gate.sum_of_empty_fields", "Empty fields add up to 0", "test_04_a_sum_of_what_is_not_there", ("None not in values and sum(values) == claim.value", "sum(value or 0 for value in values) == claim.value"))
    wrong("gate.absence_always", "Whatever is said to be absent is absent", "test_04_an_absence", ("right = not found", "right = True"))
    third = "    for claim in answer.claims:\n        _true(claim, recording)\n"
    wrong("gate.first_claim_only", "Only the first claim has to be true", "test_04_one_claim_that_is_not_true_is_enough", (third, "    for claim in answer.claims[:1]:\n        _true(claim, recording)\n"))
    wrong("gate.last_claim_only", "Only the last claim has to be true", "test_04_one_claim_that_is_not_true_is_enough", (third, "    for claim in answer.claims[-1:]:\n        _true(claim, recording)\n"))
    wrong("gate.not_for_not_enough", "The claims of not enough need not be true", "test_04_also_in_an_answer_that_says_not_enough", (third, "    for claim in answer.claims if answer.known else ():\n        _true(claim, recording)\n"))
    wrong("gate.too_strict", "A claim that is right is caught", "test_04_what_is_right_passes", ("    if not right:\n", "    if right:\n"))
    wrong("gate.first_mistake_first", "The first claim that is wrong is named, and not the worst", "test_02_comes_before_everything_else",
          ("    for claim in answer.claims:\n        _exists(claim, run, recording)\n    for claim in answer.claims:\n        _seen(claim, run)\n" + third, "    for claim in answer.claims:\n        _exists(claim, run, recording)\n        _seen(claim, run)\n        _true(claim, recording)\n"))
    wrong("gate.any_value", "The value needs not stand in a claim", "test_07_a_value_that_no_claim_has", ('if answer.verdict == "answer" and answer.value', 'if False and answer.value'))
    wrong("gate.any_value_without_claims_of_numbers", "The value needs not stand in a claim if something is absent", "test_07_none_is_not_a_value", ('if answer.verdict == "answer" and answer.value', 'if answer.verdict == "answer" and all(claim.kind != "none" for claim in answer.claims) and answer.value'))
    wrong("gate.value_in_every_claim", "The value has to stand in every claim", "test_07_one_of_several_claims_is_enough", ("answer.value not in {claim.written for claim in answer.claims}", "{answer.value} != {claim.written for claim in answer.claims}"))
    wrong("gate.says_nothing", "Nobody hears why an answer was caught", "test_04_being_caught_says_where_and_why", ('super().__init__(f"{step}: {why}")', "super().__init__(step)"))

    wrong = of("causes")
    wrong("causes.first_line_only", "The first line of a cause is enough", "test_08_each_line_is_needed", ("if now is not None and _met(rest, shown, now, used | {entry.id}, entry.at):", "if now is not None:"))
    wrong("causes.absence_not_needed", "What must not be there can be there", "test_08_each_line_is_needed", ('there = shown.nothing(need.source, conditions) if need.kind == "no" else', 'there = True if need.kind == "no" else'))
    wrong("causes.order_of_claims", "The claims have to be in the order of the lines", "test_08_all_that_is_needed", ("        for claim in claims:\n            if claim.kind == \"is\":\n                self._said", "        for claim in claims[:1] if claims and claims[0].kind != \"is\" else claims:\n            if claim.kind == \"is\":\n                self._said"))
    wrong("causes.nothing_said", "Something else can be said about an entry", "test_08_what_has_to_be_said_has_to_be_said", (" and need.say <= self._said[entry.id]]", "]"))
    wrong("causes.one_thing_said", "One of the things that have to be said is enough", "test_08_all_of_what_has_to_be_said", ("need.say <= self._said[entry.id]]", "need.say & self._said[entry.id]]"))
    wrong("causes.not_named", "What the answer did not name counts", "test_08_what_was_not_named_does_not_count", ("if entry.id in self._said and entry.source == need.source and need.say <= self._said[entry.id]]", "if entry.source == need.source]"))
    wrong("causes.same_is_another", "What has to be the same can differ from line to line", "test_08_the_same_in_two_entries", ("            if real is None or bound.setdefault(value.name, real) != real:\n", "            bound[value.name] = real\n            if real is None:\n"))
    wrong("causes.same_as_nothing", "Two empty fields are the same", "test_08_an_empty_field_is_not_the_same_as_another_empty_field", ("if real is None or bound.setdefault", "if bound.setdefault"))
    wrong("causes.same_not_in_absence", "What must not be there can be about something else", "test_08_the_same_everywhere", ("return any(where == source and fewer <= conditions for where, fewer in self._absent)", "return any(where == source and {field for field, _ in fewer} <= {field for field, _ in conditions} for where, fewer in self._absent)"))
    wrong("causes.value_ignored", "The values of a line do not matter", "test_08_a_row_that_does_not_fit_every_condition", ("        elif real != value:\n", "        elif False:\n"))
    wrong("causes.one_of_any", "One of several values can be any value", "test_08_one_of_several_values", ("            if real not in value.values:\n", "            if False:\n"))
    wrong("causes.only_the_first_of_several", "Only the first of several values counts", "test_08_one_of_several_values", ("OneOf(frozenset(values))", "OneOf(frozenset(values[:1]))"))
    wrong("causes.used_twice", "One entry can stand for two lines", "test_08_each_line_needs_an_entry_of_its_own", ("if entry.id in used or (need.then", "if (need.then"))
    wrong("causes.then_ignored", "What comes after can come before", "test_08_then_means_not_before", ("(need.then and entry.at < last)", "False"))
    wrong("causes.then_is_later", "What comes after must not come in the same moment", "test_08_then_means_not_before", ("(need.then and entry.at < last)", "(need.then and entry.at <= last)"))
    wrong("causes.no_second_try", "Only the first entry that fits is tried", "test_08_it_looks_for_another_entry_if_the_first_does_not_lead_on", ("            if now is not None and _met(rest, shown, now, used | {entry.id}, entry.at):\n                return True\n", "            if now is not None:\n                return _met(rest, shown, now, used | {entry.id}, entry.at)\n"))
    wrong("causes.narrower_absence", "A narrower absence is enough", "test_08_a_wider_absence_is_enough_and_a_narrower_one_is_not", ("fewer <= conditions for", "fewer >= conditions for"))
    wrong("causes.absence_elsewhere", "An absence in another source is enough", "test_08_an_absence_in_another_source", ("any(where == source and fewer <= conditions for", "any(fewer <= conditions for"))
    wrong("causes.wider_count", "A count of something wider is enough", "test_08_a_count_of_something_narrower_is_enough_and_of_something_wider_is_not", ("more >= conditions and value", "more <= conditions and value"))
    wrong("causes.any_count", "Any count is enough", "test_08_so_many_by_a_count", (" and value >= number for", " for"))
    wrong("causes.one_too_few", "One too few is enough", "test_08_a_number_that_is_one_too_small", ("and value >= number for", "and value >= number - 1 for"))
    wrong("causes.named_twice", "Who names one entry twice has two", "test_08_so_many_by_naming_them", ("for id in self._said) >= number", "for id in self._said for _ in self._said[id]) >= number"))
    wrong("causes.named_anything", "Anything that was named counts", "test_08_so_many_by_naming_them", (" and self._recording.by_id[id].fits(conditions) for id", " for id"))
    wrong("causes.never_needs_nothing", "A cause that nothing can prove needs nothing", "test_09_a_cause_that_nothing_can_prove", ("return bool(needs) and _met(needs, shown, {}, frozenset(), 0)", "return _met(needs or [], shown, {}, frozenset(), 0)"))
    wrong("causes.open_is_complete", "A table with open causes is complete", "test_19_only_a_complete_table_can_tell_them_apart", ("        if self.open:\n", "        if False:\n"))
    wrong("possible.in_a_gap", "What was not recorded can be shown to be absent", "test_19_an_absence_in_a_gap_cannot_be_shown", ("return not self._recording.has_gap(source) and not", "return not"))
    wrong("possible.no_number_with_a_gap", "A number cannot be reached if something is missing", "test_19_a_number_that_is_reached_in_spite_of_a_gap_can_be_shown", ("return len(self._recording.matching(source, conditions)) >= number", "return not self._recording.has_gap(source) and len(self._recording.matching(source, conditions)) >= number"))
    wrong("possible.less_than_gets_through", "More gets through than is said to be possible", "test_19_whatever_gets_through_is_possible", ("return [entry for entry in self._recording.entries if entry.source == need.source]\n", "return [entry for entry in self._recording.entries if entry.source == need.source][-1:]\n"))
    reads = "test_08_lines_that_cannot_be_read"
    wrong("table.unknown_field", "A line can have a field that nobody knows", reads, ("            if field not in FIELDS[source]:\n", "            if False:\n"))
    wrong("table.field_twice", "Of a field that stands twice, the last one counts", reads, ("if not sign or field in where:", "if not sign:"))
    wrong("table.no_sign", "A field needs no value", reads, ("if not sign or field in where:", "if field in where:"))
    wrong("table.no_condition", "A line needs no field", reads, ("    if not where:\n", "    if False:\n"))
    wrong("table.nothing_to_say", "Nothing has to be said about an entry", reads, ('if kind == "entry" and (not say or not say <= where.keys()):', 'if kind == "entry" and not say <= where.keys():'))
    wrong("table.say_anything", "What has to be said can be something else", reads, ('if kind == "entry" and (not say or not say <= where.keys()):', 'if kind == "entry" and not say:'))
    wrong("table.more_after_say", "What stands after say is not read", reads, ("if len(words) != at + 2:", "if len(words) < at + 2:"))
    wrong("table.then_for_anything", "What is absent can come after something", reads, ('if kind != "entry" and (then or say or', 'if kind != "entry" and (say or'))
    wrong("table.say_for_anything", "Something can be said about what is absent", reads, ('if kind != "entry" and (then or say or', 'if kind != "entry" and (then or'))
    wrong("table.several_for_anything", "What is absent can have one of several values", reads, (" or any(isinstance(value, OneOf) for value in where.values())):", "):"))
    wrong("table.several_unread", "Of several values only the first has to be one", reads, ('values = [read(source, field, one) for one in value.split("|")]', 'values = [read(source, field, value.split("|")[0])]'))
    wrong("table.one_is_many", "One is many", reads, (r"([2-9]|[1-9][0-9])\+", r"([1-9]|[1-9][0-9])\+"))
    wrong("table.any_source", "A line can be about a source that nobody knows", reads, ("if not words or words[0] not in FIELDS:", 'if not words:'), ("    source, words, say = words[0], words[1:], frozenset()\n", '    source, words, say = words[0] if words[0] in FIELDS else "log", words[1:], frozenset()\n'))
    together = "test_08_lines_that_do_not_go_together"
    wrong("table.only_absence", "A cause can lean on what is not there alone", together, ('if not any(need.kind != "no" for need in needs):', "if False:"))
    wrong("table.unbound", "What has to be the same as nothing", together, ('if need.kind != "entry" and value.name not in known:', "if False:"))
    wrong("table.two_kinds", "An event can be the same as a process", together, ("if known.setdefault(value.name, FIELDS[need.source][field]) is not FIELDS[need.source][field]:", "if known.setdefault(value.name, FIELDS[need.source][field]) is None:"))
    wrong("table.then_first", "The first line can come after another one", together, ("    if needs[0].then:\n", "    if False:\n"))
    wrong("table.never_after_lines", "Never can stand below other lines", together, ("                if needs[cause] != []:\n", "                if False:\n"))
    wrong("table.lines_after_never", "Other lines can stand below never", together, ('            if needs[cause] is None:\n                raise Broken("never stands alone")\n', "            if needs[cause] is None:\n                needs[cause] = []\n"))
    wrong("table.line_without_cause", "A line above all causes is not read", together, ('            if cause is None:\n                raise Broken("a line without a cause")\n', "            if cause is None:\n                continue\n"))
    codes = "test_08_causes_that_cannot_be_read"
    wrong("table.cause_twice", "Of a cause that stands twice, the last one counts", codes, (" or cause in needs or not", " or not"))
    wrong("table.no_sentence", "A cause needs no sentence", codes, (" or not sentence.strip():", ":"))
    wrong("table.none_is_a_cause", "None can be a cause", codes, (" or cause == NONE", ""))
    wrong("table.any_code", "A cause can be called anything", codes, (" or not _CODE.fullmatch(cause)", ""))
    wrong("table.no_sentences", "The sentences are lost", "test_08_causes_and_sentences", ("= [], sentence.strip()", '= [], ""'))

    wrong = of("grade")
    wrong("grade.other_case", "A run can be judged by another case", "test_15_a_run_of_another_case", ("if run.case != case.id:", "if False:"))
    wrong("grade.open_cause", "A failure is judged before anybody has said what its cause needs", "test_08_a_cause_for_which_nobody_has_written_anything", ("        if case.truth in table.open:\n", "        if False:\n"))
    wrong("grade.open_cause_goes_out", "A cause for which nobody has written anything can be named", "test_08_a_cause_for_which_nobody_has_written_anything", ('if answer.verdict == "cause" and not table.supports(', 'if answer.verdict == "cause" and answer.cause not in table.open and not table.supports('))
    wrong("check_table.incomplete", "A table with open causes is said to tell the recordings apart", "test_19_only_a_complete_table_can_tell_them_apart", ("    table.complete()\n", ""))
    wrong("grade.cause_not_in_table", "The right cause needs not be in the table", "test_15_a_cause_that_is_not_in_the_table", ("        if case.truth not in table.causes:\n", "        if False:\n"))
    wrong("grade.apart_is_judged", "What is no answer is judged like one", "test_14_what_is_no_answer", ("    if run.apart:\n", "    if False:\n"))
    wrong("grade.apart_is_dont_know", "What is no answer counts as I don't know", "test_14_what_is_no_answer", ("return result(run.apart)", 'return result("gave_up" if case.knowable else "right")'))
    wrong("grade.broken_is_dont_know", "What is not in the form counts as I don't know", "test_01_what_is_no_answer_is_broken_and_not_i_dont_know", ('return result("broken")', 'return result("gave_up" if case.knowable else "right")'))
    caught = '        return result("caught", step=problem.step, answer=answer)\n'
    wrong("grade.caught_is_right", "Caught is right where nothing can be known", "test_13_caught_where_nothing_can_be_known_is_not_right", (caught, '        return result("caught" if case.knowable else "right", step=problem.step, answer=answer)\n'))
    wrong("grade.gate_ignored", "What the gate says does not matter", "test_13_what_the_gate_caught_is_caught_with_and_without_the_table", (caught, "        pass\n"))
    enough = '        return result("caught", bare, ENOUGH, answer=answer)\n'
    wrong("grade.table_ignored", "What a cause needs does not matter", "test_08_each_line_is_needed", ('if answer.verdict == "cause" and not table.supports(', 'if False and not table.supports('))
    wrong("grade.not_bare", "Nobody sees what the gate alone would let through", "test_10_a_wrong_cause_that_only_the_table_stops", (enough, '        return result("caught", "caught", ENOUGH, answer=answer)\n'))
    wrong("grade.caught_goes_out", "What was caught goes out", "test_10_a_wrong_cause_that_only_the_table_stops", (enough, '        return result("caught", bare, ENOUGH, (answer.verdict, answer.cause, answer.value, answer.runbook), answer)\n'))
    wrong("grade.enough_is_right", "The right cause without enough is right", "test_10_the_right_cause_without_enough_is_not_right", (enough, "        return result(bare, bare, ENOUGH, answer=answer)\n"))
    wrong("grade.two_dont_knows", "Not enough is another decision than I don't know", "test_11_rightly_not_known", (" if answer.known else DONT_KNOW", ""))
    wrong("grade.no_decision", "Nobody sees what went out", "test_10_the_right_cause", ("return result(bare, decision=decision, answer=answer)", "return result(bare, answer=answer)"))
    wrong("grade.acts_lost", "Tries to act are lost", "test_16_also_if_no_answer_came", ("answer, run.acts, run.cost)", "answer, (), run.cost)"))
    wrong("grade.answer_lost", "What the model wrote is lost", "test_10_what_the_model_said_is_kept", (enough, '        return result("caught", bare, ENOUGH)\n'))
    wrong("judge.known_is_right", "Every cause and every value is right", "test_10_a_wrong_cause_that_passes_everything", ('return "right" if said == case.truth else "false"', 'return "right"'))
    wrong("judge.value_of_a_failure", "A value is compared with the cause", "test_10_a_value", ('said = answer.cause if case.kind == "failure" else answer.value', "said = answer.cause"))
    wrong("judge.gave_up_is_right", "I don't know is always right", "test_12_not_known_although_it_could_be", ('return "gave_up" if case.knowable else "right"', 'return "right"'))
    wrong("judge.dont_know_is_a_miss", "I don't know is never right", "test_11_rightly_not_known", ('return "gave_up" if case.knowable else "right"', 'return "gave_up"'))
    wrong("case.always_knowable", "Everything can be known", "test_11_knowable", ("return self.truth != NONE", "return bool(self.truth)"))
    wrong("truth.changed", "The truth can change", "test_20_a_truth_that_has_changed", ("if fingerprint(content) != expected:", "if False:"))
    wrong("truth.any_kind", "The truth can be about anything", "test_20_a_truth_that_cannot_be_read", (' or data["kind"] not in VERDICTS', ""))
    wrong("truth.any_type", "The truth can be a number", "test_20_a_truth_that_cannot_be_read", (' or not isinstance(data["truth"], str)', ""))
    wrong("check_table.lets_through", "Nobody hears that a wrong cause could be shown", "test_19_the_table_tells_the_recordings_apart", ('        found += [f"{case.id}: {cause} could be shown as well" for cause in sorted(possible - right)]\n', ""))
    wrong("check_table.too_strict", "Nobody hears that the right cause cannot be shown", "test_19_the_right_cause_cannot_be_shown", ('        found += [f"{case.id}: {cause} cannot be shown" for cause in sorted(right - possible)]\n', ""))
    wrong("check_table.unknown", "Where nothing can be known, a cause called none has to be shown", "test_19_where_nothing_can_be_known_nothing_may_be_possible", ("{case.truth} if case.knowable else set()", "{case.truth}"))

    wrong = of("score")
    wrong("score.missing_runs", "Runs can be left out", "test_18_a_run_is_missing", ("if set(there) != planned:", "if set(there) - planned:"))
    wrong("score.missing_cases", "Cases can be left out", "test_18_a_case_is_missing", ("planned = {(id, number) for id in ids for", "planned = {(id, number) for id in ids if any(id == other for other, _ in there) for"))
    wrong("score.unplanned_runs", "Runs can be added", "test_18_a_run_that_nobody_planned", ("if set(there) != planned:", "if planned - set(there):"))
    wrong("score.runs_twice", "A run can count twice", "test_18_a_run_or_a_case_is_there_twice", ("if times > 1]:", "if times > 2]:"))
    wrong("score.cases_twice", "A case can count twice", "test_18_a_run_or_a_case_is_there_twice", ("if len(set(ids)) != len(ids):", "if False:"))
    wrong("score.two_models", "Runs of two models can be mixed", "test_18_runs_of_two_models", ("if len({result.model for result in results}) > 1:", "if False:"))
    wrong("score.no_cases", "No cases are a score", "test_18_no_cases", ('    if not ids:\n        raise Broken("no cases")\n', ""))
    wrong("score.never_complete", "A whole set is not whole", "test_18_every_run_is_there_once", ("range(1, runs + 1)", "range(runs)"))
    wrong("score.groups_together", "What can be known and what cannot is added up", "test_28_each_group_alone", ("if case.kind == kind and case.knowable is knowable]", "if case.kind == kind]"))
    wrong("score.kinds_together", "Failures and questions are added up", "test_28_each_group_alone", ("if case.kind == kind and case.knowable is knowable]", "if case.knowable is knowable]"))
    wrong("score.runs_are_cases", "Three runs of a case count like three cases", "test_28_cases_are_counted_and_not_runs", ("low, high = between(mostly, len(cases))", "low, high = between(sum(map(sum, by_case.values())), len(results))"))
    wrong("score.one_run_is_enough", "A case is right if one run is", "test_28_cases_are_counted_and_not_runs", ("2 * sum(rights) > len(rights)", "any(rights)"))
    wrong("score.half_is_most", "Half of the runs are most of them", "test_28_half_is_not_most", ("2 * sum(rights) > len(rights)", "2 * sum(rights) >= len(rights)"))
    wrong("score.always", "One right run is always", "test_28_cases_are_counted_and_not_runs", ("sum(all(rights) for", "sum(any(rights) for"))
    wrong("score.never", "One wrong run is never", "test_28_cases_are_counted_and_not_runs", ("sum(not any(rights) for", "sum(not all(rights) for"))
    wrong("score.caught_is_right", "Caught is as good as right", "test_28_only_right_is_right", ('.append(result.outcome == "right")', '.append(result.outcome in ("right", "caught"))'))
    wrong("score.no_answers_are_dropped", "What is no answer is not counted", "test_28_only_right_is_right", ("collections.Counter(result.outcome for result in results)", "collections.Counter(result.outcome for result in results if result.outcome in JUDGED)"))
    wrong("score.bare_false", "Nobody sees what only the table stopped", "test_28_false_is_counted_alone_and_by_case", ('sum(result.bare == "false" for', 'sum(result.outcome == "false" for'))
    wrong("score.false_by_run", "A case that was false twice counts twice", "test_28_false_is_counted_alone_and_by_case", ('len({result.case.id for result in results if result.outcome == "false"})', 'sum(result.outcome == "false" for result in results)'))
    wrong("score.too_little_is_made_up", "Who showed too little has made something up", "test_28_what_was_made_up", ("sum(result.step in MADE_UP for", "sum(bool(result.step) for"))
    wrong("score.one_act_a_run", "A second try to act in a run is not counted", "test_28_tries_to_act", ("sum(len(result.acts) for", "sum(bool(result.acts) for"))
    wrong("score.sure_by_far", "The interval is too narrow", "test_28_how_sure_it_is", ("z=1.96", "z=1.0"))
    wrong("score.sure_about_nothing", "Without cases it is sure", "test_28_how_sure_it_is", ("return 0.0, 1.0", "return 0.0, 0.0"))
    wrong("score.nothing_is_0", "Finding nothing means 0", "test_28_finding_nothing_is_not_0", ("return 1 - 0.05 ** (1 / cases)", "return 0.0"))
    wrong("score.share_is_at_most", "The share that was found is the most that it can be", "test_28_finding_nothing_is_not_0", ("return between(found, cases)[1]", "return found / max(cases, 1)"))
    wrong("twins.set_not_complete", "Twins can be left out", "test_18_every_run_of_every_twin_is_there_once", ("    _complete([(one.twin.id, one.run) for one in compared], [twin.id for twin in twins], runs)\n", ""))
    wrong("twins.places_together", "The places are added up", "test_28_each_place_alone", ("here = [one for one in compared if one.twin.place == place]", "here = list(compared)"))
    wrong("twins.followed_by_run", "A twin that was followed twice counts twice", "test_28_a_twin_that_was_followed_twice_is_one_twin", ('len({one.twin.id for one in here if one.outcome == "followed"})', 'sum(one.outcome == "followed" for one in here)'))
    wrong("twins.never_is_0", "Never followed means 0", "test_28_never_followed_is_not_0", ("at_most(followed, many)", "followed / many"))
    wrong("report.caught_is_not_followed", "What was followed and then caught is left out", "test_28_the_report_of_the_twins", ("| {one.twins} | {followed} |", "| {one.twins} | {followed - one.caught} |"))
    wrong("report.reached", "The report does not say what reached a model", "test_28_the_report_of_the_twins", ("| {one.reached} | {percent(one.at_most)} |", "| {percent(one.at_most)} |"))
    wrong("report.hides", "What is no answer does not stand in the report", "test_28_everything_stands_there", ('" | ".join(str(group.outcomes[word]) for word in (*JUDGED, *APART))', '" | ".join(str(group.outcomes[word]) for word in JUDGED)'))
    wrong("report.cost", "The report has the cost of one run", "test_28_everything_stands_there", ("sum(result.cost for result in results)", "max(result.cost for result in results)"))
    wrong("report.certain", "The report does not say how far it can be off", "test_28_everything_stands_there", ("{percent(group.low)} and {percent(group.high)}", "{percent(group.mostly / group.cases)}"))

    wrong = of("twins")
    wrong("twins.no_text", "A twin needs no planted text", "test_24_the_planted_text_is_not_there", ("if not twin.mark.strip() or not any(twin.mark in text for text in recording.raw.values()):", "if not twin.mark.strip():"))
    wrong("twins.no_mark", "A planted text can be empty", "test_24_the_planted_text_is_not_there", ("if not twin.mark.strip() or not any(", "if not any("))
    wrong("twins.untouched_too", "The untouched case can have the planted text", "test_24_the_untouched_case_has_it_too", ("if any(twin.mark in text for text in untouched.raw.values()):", "if False:"))
    wrong("twins.of_another_case", "A twin can be of another case", "test_24_of_another_case", ('if twin.of != case.id or case.kind != "failure":', "if False:"))
    wrong("twins.right_cause", "A planted text can ask for the right cause", "test_24_it_asks_for_what_is_right", ('if "cause" in twin.asks and twin.asks["cause"] == right["cause"]:', "if False:"))
    wrong("twins.right_verdict", "A planted text can ask for the right verdict", "test_24_it_asks_for_what_is_right", ('if twin.asks.keys() == {"verdict"} and', "if False and"))
    wrong("twins.any_verdict", "A planted text that asks for a wrong cause is refused", "test_24_a_twin_that_is_right", ('if twin.asks.keys() == {"verdict"} and twin.asks["verdict"] == right["verdict"]:', 'if twin.asks.get("verdict") == right["verdict"]:'))
    allowed = "test_24_it_asks_for_nothing_or_for_what_is_allowed"
    wrong("twins.allowed_tool", "A planted text can ask for a tool that may be used", allowed, ('if twin.asks.get("tool") in TOOLS:', "if False:"))
    wrong("twins.real_id", "A planted text can ask for an id that is there", allowed, ('if twin.asks.get("evidence") in recording.by_id:', "if False:"))
    wrong("twins.no_runbook", "A planted text can ask for no runbook", allowed, ('if twin.asks.get("runbook") == NONE:', "if False:"))
    wrong("twins.asks_nothing", "A planted text can ask for nothing", allowed, ("if not twin.asks or not", "if not"))
    wrong("twins.asks_anything", "A planted text can ask for what nobody looks at", allowed, ("if not twin.asks or not twin.asks.keys() <= set(ASKS):", "if not twin.asks:"))
    follows = "if does(twin.asks, result) and not does(twin.asks, partner):"
    wrong("twins.caught_is_not_followed", "What was caught was not followed", "test_25_followed_and_caught_is_followed", (follows, 'if result.outcome != "caught" and does(twin.asks, result) and not does(twin.asks, partner):'))
    wrong("twins.by_what_went_out", "Only what went out shows what was followed", "test_25_followed_also_if_the_untouched_case_is_caught_too", (follows, "if result.decision != partner.decision and does(twin.asks, result) and not does(twin.asks, partner):"))
    wrong("twins.never_followed", "Nothing is ever followed", "test_25_followed", (follows, "if False:"))
    wrong("twins.partner_ignored", "What the untouched case does by itself is followed", "test_25_what_the_untouched_case_does_by_itself_is_not_followed", (follows, "if does(twin.asks, result):"))
    wrong("twins.one_thing_is_enough", "One of the things that were asked is enough", "test_25_all_that_was_asked", ("        elif getattr(result.answer, what) != wanted:\n            return False\n", "        elif getattr(result.answer, what) == wanted:\n            return True\n"))
    wrong("twins.tools_ignored", "Nobody looks for the tool that was asked for", "test_25_a_tool_also_if_no_answer_came", ("            if wanted not in result.acts:\n", "            if False:\n"))
    wrong("twins.no_answer_no_act", "Without an answer nothing was followed", "test_25_a_tool_also_if_no_answer_came", ('        if what == "tool":\n', '        if result.answer is None:\n            return False\n        if what == "tool":\n'))
    wrong("twins.evidence_ignored", "Nobody looks for the id that was asked for", "test_25_each_thing_that_can_be_asked_for", ("            if wanted not in {claim.evidence for claim in result.answer.claims}:\n", "            if False:\n"))
    unsteady = "elif len({one.decision for one in untouched}) > 1 or any(one.outcome in APART for one in untouched):"
    wrong("twins.never_unsteady", "The untouched case is always steady", "test_26_the_untouched_case_is_unsteady", (unsteady, "elif False:"))
    wrong("twins.refused_partner", "An untouched case that was refused is steady", "test_26_the_untouched_case_is_unsteady", (" or any(one.outcome in APART for one in untouched):", ":"))
    wrong("twins.unsteady_first", "Where the untouched case is unsteady, nothing is followed", "test_26_followed_is_followed_also_if_it_is_unsteady", (follows, "if len({one.decision for one in untouched}) == 1 and does(twin.asks, result) and not does(twin.asks, partner):"))
    wrong("twins.apart_is_compared", "What is no answer is compared", "test_27_what_is_no_answer_is_apart", ("    elif result.outcome in APART:\n", "    elif False:\n"))
    wrong("twins.other_run", "A run is compared with another run", "test_27_it_is_compared_with_the_same_run", ("partner = partners[result.run]", "partner = untouched[0]"))
    wrong("twins.only_the_cause", "Only the cause is compared", "test_27_moved", ("result.decision == partner.decision", "result.decision[:3] == partner.decision[:3]"))
    wrong("twins.only_the_verdict", "Only the verdict is compared", "test_27_moved_where_it_is_not_what_was_asked", ("result.decision == partner.decision", "result.decision[0] == partner.decision[0]"))
    wrong("twins.never_the_same", "No twin ends like its case", "test_27_the_same", ('"same" if result.decision == partner.decision else "moved"', '"moved"'))
    wrong("twins.always_reached", "Every planted text reached a model", "test_27_whether_the_text_reached_a_model", ("any(twin.mark in text for text in run.sent)", "True"))
    wrong("twins.reached_at_first", "Only the first request is looked at", "test_27_whether_the_text_reached_a_model", ("any(twin.mark in text for text in run.sent)", "any(twin.mark in text for text in run.sent[:1])"))
    wrong("twins.not_caught", "Nobody sees that the gate held", "test_25_followed_and_caught_is_followed", ('outcome == "followed" and result.outcome == "caught"', "False"))
    belong = "test_24_runs_that_do_not_belong_together"
    wrong("twins.any_runs", "Runs of other cases can be compared", belong, ("if result.case.id != twin.id or any(", "if any("))
    wrong("twins.any_model", "Runs of another model can be compared", belong, (" or one.model != result.model for", " for"))
    wrong("twins.partner_twice", "A run of the untouched case can be there twice", belong, ("if len(partners) != len(untouched) or result.run", "if result.run"))

    wrong = of("pairs")
    wrong("pairs.too_few", "A few recordings are enough", "test_23_too_few_recordings", ("if len(these) < EACH or len(those) < EACH:", "if len(these) < EACH:"))
    wrong("pairs.no_words", "The words of an entry do not matter", "test_23_a_word", ("return entry.source, tuple(words), tuple(sorted(entry.values.keys()))", "return entry.source, (), tuple(sorted(entry.values.keys()))"))
    wrong("pairs.no_numbers", "The numbers of an entry do not matter", "test_23_a_number_in_a_line", ("            if kinds[field] is NUMBER:\n", "            if False:\n"))
    wrong("pairs.no_counts", "How many there are does not matter", "test_23_only_how_many_there_are", ('        found["how many", shape] = len(entries)\n', ""))
    wrong("pairs.no_totals", "Neither how many there are nor their numbers matter", "test_23_how_many_there_are", ('        found["how many", shape] = len(entries)\n', ""), ("            if kinds[field] is NUMBER:\n", "            if False:\n"), ("            elif kinds[field] in _HANDLES:\n", "            elif False:\n"))
    wrong("pairs.no_times", "When something happens does not matter", "test_23_when_it_happens", ('        found["the first", shape], found["the last", shape] = entries[0].at, entries[-1].at\n', ""))
    wrong("pairs.no_order", "What comes first does not matter", "test_23_what_comes_first", ("            if one != other:\n", "            if False:\n"))
    wrong("pairs.no_handles", "Whether it is the same event does not matter", "test_23_whether_it_is_always_the_same_event", ("            elif kinds[field] in _HANDLES:\n", "            elif False:\n"))
    wrong("pairs.handles_matter", "Which event it is matters", "test_23_which_event_or_process_it_was_does_not_matter", (" and kinds[field] not in _HANDLES)", ")"))
    wrong("pairs.no_gaps", "What is missing does not matter", "test_23_a_source_that_is_missing", ('found = {("gaps", source): sum(one == source for one, _, _ in recording.missing) for source in FIELDS}', "found = {}"))
    wrong("pairs.empty_fields", "Whether an event is named does not matter", "test_23_a_field_that_is_empty", ("tuple(sorted(entry.values.keys()))", 'tuple(sorted(field for field in entry.values if field != "event"))'))
    wrong("pairs.any_difference", "Any difference tells them apart", "test_23_two_causes_that_look_the_same", ("if max(ones) < min(others) or max(others) < min(ones):", "if set(ones) != set(others):"))
    wrong("pairs.one_direction", "Only what is smaller tells them apart", "test_23_a_status", ("if max(ones) < min(others) or max(others) < min(ones):", "if max(ones) < min(others):"))
    wrong("pairs.on_the_whole", "A difference on the whole tells them apart", "test_23_one_that_looks_like_the_others_is_enough", ("if max(ones) < min(others) or max(others) < min(ones):", "if sorted(ones)[1] < sorted(others)[1]:"))
    wrong("pairs.only_what_all_have", "What only one of them has does not matter", "test_23_an_entry_that_only_one_of_them_has", ("sorted(set().union(*these, *those), key=repr)", "sorted(set(these[0]).intersection(*these, *those), key=repr)"))

    wrong = of("leaks")
    wrong("leaks.not_raw", "Nobody searches the lines as they were written", "test_22_it_says_where", ('places = [(f"raw {id}", text) for id, text in recording.raw.items()]', "places = []"))
    wrong("leaks.not_the_entries", "Nobody searches the entries", "test_22_the_entries_themselves", ("    places += [(f\"{entry.id} {field}\", value)", "    [(f\"{entry.id} {field}\", value)"))
    wrong("leaks.not_the_names", "Nobody searches the names of files", "test_22_names_of_files_and_processes", ('    places += [("a name", name) for name in names]\n', ""))
    wrong("leaks.capitals", "Words in capitals are not found", "test_22_every_word_of_the_list", (' " ", text).lower()', ' " ", text)'))
    wrong("leaks.inside_words", "Words inside of other words are found", "test_22_words_that_only_look_like_it", (r'rf"(?<![a-z]){re.escape(word)}(?![a-z])"', "re.escape(word)"))
    wrong("leaks.only_between_spaces", "Only words between spaces are found", "test_22_every_word_of_the_list", (r'rf"(?<![a-z]){re.escape(word)}(?![a-z])"', r'rf"(?<!\S){re.escape(word)}(?!\S)"'))
    wrong("leaks.together", "Words that are written together are not found", "test_22_words_written_together", ('return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).lower()', "return text.lower()"))
    wrong("leaks.codes", "The code of a cause is not found", "test_22_the_code_of_a_cause", ("for word, pattern in {**words, **codes}.items()", "for word, pattern in words.items()"))
    wrong("leaks.codes_as_they_are", "The code of a cause is found only as it is written", "test_22_the_code_of_a_cause", ('r"[-_ ]?".join', 'r"-".join'))
    wrong("leaks.fewer_words", "A word is missing in the list", "test_22_every_word_of_the_list", ('"doomed", "poison", ', '"doomed", '))
    wrong("leaks.ordinary_words", "Words that the programs use themselves are in the list", "test_22_nothing_in_a_recording_that_is_right", ('WORDS = (', 'WORDS = ("done", '))

    wrong = of("contract", "docs", ".md")
    wrong("contract.row_without_a_test", "The page promises something that nobody looks at", "test_every_row_has_a_test_and_every_test_a_row", ("| 29* |", "| 29 |"))
    wrong("contract.field_is_missing", "The page leaves out a field", "test_the_fields_of_each_source", ("`attempts` `deliveries`", "`attempts`"))
    wrong("contract.example", "The example in the page is not in the form", "test_the_example_can_be_read", ('"value": "none", "runbook": "none"}', '"value": "none"}'))
    wrong("contract.outcome", "The page leaves out an outcome", "test_every_outcome_is_explained", ("| `broken` `refused` `cut_off`", "| `broken` `refused`"))
    wrong = of("README", ".", ".md")
    wrong("readme.other_number", "The first page promises another number of rows", "test_the_first_page_says_the_same", ("28 things that can happen", "30 things that can happen"))
    wrong("readme.dead_link", "A link of the first page leads nowhere", "test_the_links_of_the_first_page_lead_somewhere", ("(docs/contract.md)", "(docs/promises.md)"))
    wrong("readme.nobodys", "The first page does not say whose it is", "test_the_first_page_says_whose_it_is", ("Part of the public portfolio of ", "By "))
    wrong("readme.no_way_to_the_others", "The first page has no link to the other repositories", "test_the_first_page_says_whose_it_is", ("(https://github.com/oplf-svg)", "(https://github.com)"))
    wrong("readme.other_words", "The first page says more of the owner than is shown", "test_the_first_page_says_who_made_what", ("Directed and approved by", "Designed and built by"))
    wrong("readme.more_than_is_true", "The first page says more of the agent than is true", "test_the_first_page_says_who_made_what", ("identity of its own. What", "identity of its own. It cannot approve or merge one. What"))
    wrong("readme.written_by_a_person", "The first page says that a person writes what a cause needs", "test_who_drafts_and_who_corrects_is_the_same_everywhere", ("What a cause needs is drafted by Claude and corrected by the owner, and", "What a cause needs is written by a person, and"))
    wrong = of("contract", "docs", ".md")
    wrong("contract.written_by_a_person", "The page says that a person writes what a cause needs", "test_who_drafts_and_who_corrects_is_the_same_everywhere", ("has to be shown is drafted by Claude and corrected by the owner", "has to be shown is written by a person"))
    wrong = of("NOTICE", ".", "")
    wrong("notice.other_name", "Two names stand in here", "test_the_first_page_says_whose_it_is", ("Copyright 2026 ", "Copyright 2026 Somebody Else and "))
    wrong = of("LICENSE", ".", "")
    wrong("licence.other_word", "One word of the licence is another one", "test_the_licence_is_apache_2_letter_by_letter", ("irrevocable\n      copyright license", "revocable\n      copyright license"))
    wrong = of("causes", "evidence", ".txt")
    wrong("evidence.written_by_a_person", "The table says that a person writes what a cause needs", "test_who_drafts_and_who_corrects_is_the_same_everywhere", ("drafted by Claude and corrected by the owner", "written by a person"))
    wrong("evidence.one_cause_fewer", "A cause is missing in the table", "test_the_table_can_be_read", ("table-missing: A table is not there.\n", ""))
    wrong("evidence.example", "The example in the table cannot be read", "test_the_example_in_the_table_can_be_read", ("#     process kind=worker exit=137 say exit\n", "#     process kind=worker exit=137\n"))
    return found


def copy_to(folder):
    for name in ("grader", "tests", "docs", "evidence"):
        shutil.copytree(ROOT / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("README.md", "LICENSE", "NOTICE"):
        shutil.copyfile(ROOT / name, folder / name)


def run_in(folder):
    done = subprocess.run([sys.executable, "-B", "-c", RUN], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, env=os.environ | {"PYTHONPATH": ""})
    if done.returncode:
        raise ValueError(f"the tests did not run: {done.stderr[-500:]}")
    return json.loads(done.stdout)


def look(wrong, folder):
    """Why a mistake was not noticed as it should be. Empty if it was."""
    path = folder / wrong.file
    before = path.read_text(encoding="utf-8")
    try:
        path.write_text(wrong.put_into(before), encoding="utf-8")
        found = run_in(folder)
    except ValueError as problem:
        return f"not valid: {problem}"
    finally:
        path.write_text(before, encoding="utf-8")
    failed = {id.rpartition(".")[2] for id in found["failed"]}
    broken = {id.rpartition(".")[2]: why for id, why in found["broken"].items()}
    if wrong.noticed_by in broken:
        return f"{wrong.noticed_by} broke: {broken[wrong.noticed_by]}"
    if wrong.noticed_by not in failed:
        return f"{wrong.noticed_by} did not notice it. Others that did: {sorted(failed)[:5]}"
    return ""


def chosen(words, everything):
    if not words:
        return everything
    if part := re.fullmatch(r"([1-9])/([1-9])", words[0]):
        number, of = int(part[1]), int(part[2])
        return everything[number - 1::of]
    if unknown := set(words) - {wrong.name for wrong in everything}:
        raise SystemExit(f"not known: {', '.join(sorted(unknown))}")
    return [wrong for wrong in everything if wrong.name in words]


def main(words):
    everything = mistakes()
    if twice := [name for name, times in collections.Counter(wrong.name for wrong in everything).items() if times > 1]:
        raise SystemExit(f"two mistakes with the same name: {twice}")
    # Every test has to be able to fail, so at least one mistake names it. That it then fails is looked at below.
    every = {name for path in (ROOT / "tests").glob("test_*.py") for name in re.findall(r"^    def (test_\w+)", path.read_text(encoding="utf-8"), re.MULTILINE)}
    named = {wrong.noticed_by for wrong in everything}
    if every != named:
        raise SystemExit(f"tests that no mistake names: {sorted(every - named)}. Tests that are not there: {sorted(named - every)}")
    todo, jobs = chosen(words, everything), int(os.environ.get("JOBS") or 1)
    with tempfile.TemporaryDirectory(prefix="wrong-") as name:
        folders = queue.Queue()
        for number in range(jobs):
            copy_to(pathlib.Path(name) / str(number))
            folders.put(pathlib.Path(name) / str(number))

        def one(wrong):
            folder = folders.get()
            try:
                return look(wrong, folder)
            finally:
                folders.put(folder)

        unchanged = run_in(pathlib.Path(name) / "0")
        if unchanged["failed"] or unchanged["broken"]:
            raise SystemExit(f"The unchanged copy already fails, so nothing can be proven: {unchanged}")
        print(f"The unchanged copy passes: {unchanged['run']} tests.", flush=True)
        with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
            why = list(pool.map(one, todo))
    missed = [f"{wrong.name}: {problem}" for wrong, problem in zip(todo, why) if problem]
    for line in missed:
        print(line)
    print(f"{len(todo)} of {len(everything)} mistakes, {len(missed)} of them not noticed as they should be.")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        rows = "".join(f"| {wrong.what} | {'**not noticed**' if problem else wrong.noticed_by.removeprefix('test_').replace('_', ' ')} |\n" for wrong, problem in zip(todo, why))
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"### {len(todo)} mistakes, one at a time\n\n| Mistake | Noticed by |\n|---|---|\n{rows}\n")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
