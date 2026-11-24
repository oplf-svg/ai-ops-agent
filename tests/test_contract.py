"""That the page, the table and the code say the same."""

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


class Page(unittest.TestCase):
    def test_every_row_has_a_test_and_every_test_a_row(self):
        tests = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
        rows = {int(number) for number in re.findall(r"^\| (\d+) \|", PAGE, re.MULTILINE)}
        self.assertEqual(rows, {int(number) for number in re.findall(r"def test_(\d\d)_", tests)})
        # What is not built yet has a star and no test.
        self.assertEqual(sorted(rows), list(range(1, 29)))

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
