"""A recording: what could be seen while one thing went wrong. It is checked whole before anything relies on it."""

import dataclasses
import hashlib

from grader import Broken, strict
from grader.fields import FIELDS, LETTER, NUMBER, is_id

FILES = ("entries.jsonl", "missing.json", "raw.jsonl")
META = {"files", "platform", "recorder", "seed"}


@dataclasses.dataclass(frozen=True)
class Entry:
    """One thing that was seen. The time is in milliseconds since the start."""

    id: str
    at: int
    source: str
    values: dict

    def get(self, field):
        return self.values.get(field)

    def fits(self, conditions):
        return all(self.values.get(field) == value for field, value in conditions)


class Recording:
    """The entries in the order of time, and the stretches in which a source was not recorded."""

    def __init__(self, entries, missing=(), raw=None):
        self.entries = tuple(entries)
        self.missing = tuple(missing)
        # The lines as they were written, by id. Only the search for leaks and the twins look at them.
        self.raw = dict(raw or {})
        self.by_id = {entry.id: entry for entry in self.entries}
        if len(self.by_id) != len(self.entries):
            raise Broken("two entries have the same id")
        if any(one.at > other.at for one, other in zip(self.entries, self.entries[1:])):
            raise Broken("the entries are not in the order of time")
        if not self.raw.keys() <= self.by_id.keys():
            raise Broken("a raw line has no entry")

    def matching(self, source, conditions):
        return [entry for entry in self.entries if entry.source == source and entry.fits(conditions)]

    def has_gap(self, source):
        return any(gap_source == source for gap_source, _, _ in self.missing)


def read_entry(line):
    """One entry. Whatever is not in the list of fields is refused, so free text cannot get in."""
    try:
        data = strict.loads(line, 2_000)
    except ValueError as problem:
        raise Broken(f"not an entry: {problem}") from None
    if not isinstance(data, dict):
        raise Broken("not an entry: not an object")
    id, at, source = (data.pop(name, None) for name in ("id", "at", "source"))
    if not isinstance(source, str) or source not in FIELDS:
        raise Broken("an entry without a source that is known")
    if not is_id(id, LETTER[source]):
        raise Broken(f"an entry of {source} without a right id")
    if not NUMBER.fits(at):
        raise Broken(f"{id} has no right time")
    for field, value in data.items():
        if field not in FIELDS[source] or not FIELDS[source][field].fits(value):
            raise Broken(f"{id} has something that a {source} cannot have: {field[:20]}")
    return Entry(id, at, source, data)


def read_gap(data):
    if not isinstance(data, dict) or set(data) != {"source", "from", "to"} or not isinstance(data["source"], str) or data["source"] not in FIELDS:
        raise Broken("a gap has a source, a start and an end")
    if not NUMBER.fits(data["from"]) or not NUMBER.fits(data["to"]) or data["from"] > data["to"]:
        raise Broken("a gap that ends before it starts")
    return data["source"], data["from"], data["to"]


def fingerprint(content):
    return hashlib.sha256(content).hexdigest()


def _lines(content):
    # Not splitlines(): that also cuts at characters which may stand inside a text.
    return content.decode("utf-8").removesuffix("\n").split("\n") if content else []


def load(folder, expected):
    """Reads a folder. `expected` is the fingerprint of its meta.json, which has the fingerprints of all the others."""
    meta = (folder / "meta.json").read_bytes()
    if fingerprint(meta) != expected:
        raise Broken(f"{folder.name}: meta.json has changed")
    try:
        meta = strict.loads(meta.decode("utf-8"), 5_000)
    except ValueError as problem:
        raise Broken(f"{folder.name}: meta.json: {problem}") from None
    if not isinstance(meta, dict) or set(meta) != META or not isinstance(meta["files"], dict) or set(meta["files"]) != set(FILES):
        raise Broken(f"{folder.name}: meta.json is not complete")
    if {path.name for path in folder.iterdir()} != {"meta.json", *FILES}:
        raise Broken(f"{folder.name}: a file too many or too few")
    content = {}
    for name in FILES:
        content[name] = (folder / name).read_bytes()
        if fingerprint(content[name]) != meta["files"][name]:
            raise Broken(f"{folder.name}: {name} has changed")
    try:
        entries = [read_entry(line) for line in _lines(content["entries.jsonl"])]
        missing = strict.loads(content["missing.json"].decode("utf-8"), 20_000)
        raw = [strict.loads(line, 400_000) for line in _lines(content["raw.jsonl"])]
    except ValueError as problem:
        raise Broken(f"{folder.name}: {problem}") from None
    if not isinstance(missing, list):
        raise Broken(f"{folder.name}: missing.json is not a list")
    if not all(isinstance(line, dict) and set(line) == {"id", "text"} and all(isinstance(text, str) for text in line.values()) for line in raw):
        raise Broken(f"{folder.name}: a raw line is an id and a text")
    if len({line["id"] for line in raw}) != len(raw):
        raise Broken(f"{folder.name}: two raw lines have the same id")
    return Recording(entries, map(read_gap, missing), {line["id"]: line["text"] for line in raw})
