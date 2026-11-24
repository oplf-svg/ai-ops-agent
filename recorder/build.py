"""The platform at its commit: as it is, and with one of its own deliberate mistakes in it."""

import pathlib
import shutil
import subprocess
import sys

from grader import Broken

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLATFORM = ROOT / "webhook-platform"
BUILD = ROOT / "build"

# Its own tools: a database that can be killed, and the mistakes that its tests have to notice.
sys.path.insert(0, str(PLATFORM / "crash"))


def commit():
    found = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PLATFORM, check=True, capture_output=True, text=True).stdout.strip()
    if found != (ROOT / "webhook-platform.commit").read_text(encoding="utf-8").strip():
        raise Broken("webhook-platform stands at another commit")
    return found


class Version:
    """Where the two programs of one version lie, and its statements if they are others than those inside."""

    def __init__(self, programs, statements=None):
        self.programs, self.statements = programs, statements


def _mistakes():
    import wrong

    return {one.name: one for one in [*wrong.wrong_sql(), *wrong.wrong_code()]}


def _publish(source, out):
    for part in ("api", "worker"):
        # Without its debug files no line of a log has the path of a file in it.
        done = subprocess.run(
            ["dotnet", "publish", f"src/Platform.{part.capitalize()}", "--configuration", "Release", "--verbosity", "quiet", "--artifacts-path", str(out / "artifacts"), "--output", str(out / part),
             "-p:Faults=true", "-p:DebugType=none", "-p:DebugSymbols=false"], cwd=source, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        if done.returncode:
            raise Broken(f"it does not build: {done.stdout[-1500:]}")


class Versions:
    """Builds each version once, when it is first asked for."""

    def __init__(self):
        self._made = {}

    def get(self, mistake=None):
        if mistake not in self._made:
            self._made[mistake] = self._make(mistake)
        return self._made[mistake]

    def _make(self, mistake):
        number = len(self._made)
        out = BUILD / "versions" / str(number)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        if mistake is None:
            _publish(PLATFORM, out)
            return Version(out)
        wrong = _mistakes()[mistake]
        path = PLATFORM / wrong.file
        text = wrong.put_into(path.read_text(encoding="utf-8"))
        if wrong.file.startswith("db/"):
            # A statement is read while the programs run, so nothing has to be built.
            statements = out / "statements"
            shutil.copytree(PLATFORM / "db", statements)
            # Without the first lines, which say what is wrong with it.
            (statements / path.name).write_text("\n".join(line for line in text.split("\n") if not line.startswith("-- ")), encoding="utf-8")
            return Version(self.get().programs, statements)
        source = out / "source"
        shutil.copytree(PLATFORM, source, ignore=shutil.ignore_patterns(".git", "build", "bin", "obj", "TestResults", "__pycache__"))
        (source / wrong.file).write_text(text, encoding="utf-8")
        _publish(source, out)
        return Version(out)
