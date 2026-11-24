"""The script that the required check runs."""

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ONE = "import unittest\n\n\nclass One(unittest.TestCase):\n    def test_one(self):\n        self.assertEqual(1, {})\n"


class TestsScript(unittest.TestCase):
    def go(self, number=1, **files):
        """Runs the real script in a folder of its own, from somewhere else. A text that starts with -> is a link, and None is a folder."""
        with tempfile.TemporaryDirectory() as folder:
            script = pathlib.Path(folder, ".github", "scripts", "tests.sh")
            script.parent.mkdir(parents=True)
            shutil.copy(ROOT / ".github" / "scripts" / "tests.sh", script)
            for name, text in {"tests/__init__.py": "", "tests/test_one.py": ONE.format(number), "elsewhere": "not for everybody\n", **files}.items():
                path = pathlib.Path(folder, name)
                path.parent.mkdir(exist_ok=True)
                if text is None:
                    path.mkdir()
                elif text.startswith("->"):
                    path.symlink_to(text[2:])
                else:
                    path.write_text(text, encoding="utf-8")
            done = subprocess.run(["bash", str(script)], cwd="/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            return done.returncode, done.stdout

    def test_the_tests_are_run(self):
        code, said = self.go()
        self.assertEqual((code, "Ran 1 test" in said, "merged" in said), (0, True, False), said)
        code, said = self.go(number=2)
        self.assertEqual((code != 0, "AssertionError: 1 != 2" in said), (True, True), said)

    def test_a_branch_that_has_to_wait_is_red(self):
        for text, words in {"Waits for the owner, until 1 December.\nmore\n": "Waits for the owner, until 1 December.", "": ""}.items():
            code, said = self.go(HOLD=text)
            # It comes last, so everything else was seen.
            self.assertEqual((code, "Ran 1 test" in said, said.split("\n")[-2]), (1, True, f"Not to be merged yet: {words}"), said)

    def test_what_is_not_a_plain_file_makes_it_wait_as_well(self):
        for what in ("->elsewhere", "->nowhere", None):
            code, said = self.go(HOLD=what)
            # The log is public, so nothing is said of where a link leads.
            self.assertEqual((code, "HOLD is not a plain file." in said, "not for everybody" in said), (1, True, False), said)

    def test_only_that_file_makes_it_wait(self):
        code, said = self.go(**{"HOLDER": "x", "hold.txt": "x", "tests/HOLD": "x"})
        self.assertEqual((code, "merged" in said), (0, False), said)
