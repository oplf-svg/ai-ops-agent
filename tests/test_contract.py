"""That the page, the table and the code say the same."""

import hashlib
import pathlib
import re
import unittest

from grader.answer import read_answer
from grader.causes import read_table
from grader.fields import FIELDS
from grader.grade import APART, JUDGED

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "docs" / "contract.md").read_text(encoding="utf-8")
CAUSES = (ROOT / "evidence" / "causes.txt").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
RUNBOOKS = (ROOT / "evidence" / "runbooks.txt").read_text(encoding="utf-8")


class Page(unittest.TestCase):
    def test_every_row_has_a_test_and_every_test_a_row(self):
        tests = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
        rows = {int(number) for number in re.findall(r"^\| (\d+) \|", PAGE, re.MULTILINE)}
        self.assertEqual(rows, {int(number) for number in re.findall(r"def test_(\d\d)_", tests)})
        # What is not built yet has a star and no test.
        self.assertEqual(sorted(rows), list(range(1, 39)))

    def test_the_fields_of_each_source(self):
        for source, fields in FIELDS.items():
            row = re.search(rf"^\| `{source}` \|.*\|(.*)\|$", PAGE, re.MULTILINE)
            self.assertEqual(re.findall(r"`(\w+)`", row[1]), list(fields), source)

    def test_the_example_can_be_read(self):
        example = read_answer(re.search(r"```json\n(.*?)```", PAGE, re.DOTALL)[1], "failure", read_table(CAUSES).causes, ())
        self.assertEqual([claim.kind for claim in example.claims], ["is", "none"])

    def test_every_outcome_is_explained(self):
        explained = re.search(r"## What comes of a run\n(.*?)\n## ", PAGE, re.DOTALL)[1]
        self.assertEqual(set(re.findall(r"`(\w+)`", explained)), {*JUDGED, *APART})


class FirstPage(unittest.TestCase):
    def test_the_first_page_says_the_same(self):
        rows, later = re.findall(r"^\| \d+ \|", PAGE, re.MULTILINE), re.findall(r"^\| \d+\* \|", PAGE, re.MULTILINE)
        self.assertIn(f"{len(rows)} things that can happen, and what must be true afterwards. Four more come later", README)
        self.assertEqual(len(later), 4)

    def test_the_links_of_the_first_page_lead_somewhere(self):
        links = re.findall(r"\]\(([a-z][^):]*)\)", README)
        self.assertGreater(len(links), 3)
        for link in links:
            self.assertTrue((ROOT / link).exists(), link)


class WhoMadeThis(unittest.TestCase):
    """The name stands in NOTICE and is the same everywhere. What is said of who did what is the same as well."""

    def name(self):
        (name,) = re.findall(r"^Copyright [0-9]{4} (\S.*\S)$", NOTICE, re.MULTILINE)
        return name

    def test_the_first_page_says_whose_it_is(self):
        line = README.split("\n")[2]
        self.assertTrue(line.startswith(f"Part of the public portfolio of {self.name()}. "), line)
        self.assertIn("(https://github.com/oplf-svg)", line)

    def test_the_first_page_says_who_made_what(self):
        text = " ".join(README.split())
        self.assertIn(
            f"Directed and approved by {self.name()}. Code, tests and texts are written by Claude, an AI agent that proposes its changes under an "
            "identity of its own. ", text)
        # More than is shown.
        self.assertNotRegex(text.lower(), "cannot approve|cannot merge|approve or merge|designed by|built by|reviewed by")

    def test_who_drafts_and_who_corrects_is_the_same_everywhere(self):
        for text in (README, PAGE, CAUSES, RUNBOOKS):
            said = re.sub(r"[\s#]+", " ", text).lower()
            self.assertIn("drafted by claude and corrected by the owner", said)
            self.assertNotIn("written by a person", said)

    def test_the_rule_for_two_causes_stands_where_it_is_needed(self):
        for text in (README, PAGE):
            self.assertIn("proposed by claude and decided by the owner", re.sub(r"\s+", " ", text).lower())
        for text in (PAGE, CAUSES):
            said = re.sub(r"[\s#]+", " ", text).lower()
            self.assertIn("answer is the mistake in the program", said)
            self.assertIn("the agent is told so", said)

    def test_the_licence_is_apache_2_letter_by_letter(self):
        self.assertEqual(hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest(), "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4")


class TableOfCauses(unittest.TestCase):
    def test_the_table_can_be_read(self):
        table = read_table(CAUSES)
        never = [cause for cause, needs in table._needs.items() if needs is None]
        self.assertEqual((len(table.causes), len(never)), (50, 20))
        for sentence in table.sentences.values():
            self.assertRegex(sentence, r"^[A-Z].*\.$")

    def test_the_example_in_the_table_can_be_read(self):
        example = "\n".join(line.removeprefix("#   ") for line in CAUSES.split("\n") if line.startswith("#   "))
        self.assertEqual(read_table(example).causes, ("kettle-boiled-dry",))
