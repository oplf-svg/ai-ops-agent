"""Writes one recording: the wall that puts handles in the place of names, the ids, the files and their fingerprints."""

import json
import secrets

from grader import Broken, leaks
from grader.fields import LETTER
from grader.recording import fingerprint, load

# The letters of an id. Nobody finds one by trying.
LETTERS = "abcdefghijklmnopqrstuvwxyz234567"


class Handles:
    """What stands for a name. The numbers are drawn when all names are known, so a number says nothing about what came first."""

    def __init__(self, random):
        self._random, self._names, self._drawn = random, {}, {}

    def note(self, letter, name):
        self._names.setdefault(letter, {})[name] = None

    def draw(self):
        for letter, names in self._names.items():
            numbers = list(range(1, len(names) + 1))
            self._random.shuffle(numbers)
            self._drawn[letter] = {name: f"{letter}{number}" for name, number in zip(names, numbers)}

    def of(self, letter, name):
        return self._drawn[letter][name]


# Which fields hold a name, with the letter of its handle and what the name is told apart by.
NAMES = {
    "event": ("e", lambda values: (values["feed"], values["event"])),
    "order": ("o", lambda values: (values["feed"], values["order"])),
    "item": ("i", lambda values: values["item"]),
    "process": ("p", lambda values: values["process"]),
}


def behind_the_wall(noted, random):
    """The same entries with handles. A total belongs to a shop and has no such names."""
    handles = Handles(random)
    for _, _, values, _ in noted:
        for field, (letter, key) in NAMES.items():
            if field in values:
                handles.note(letter, key(values))
    handles.draw()
    return [
        (at, source, {field: handles.of(NAMES[field][0], NAMES[field][1](values)) if field in NAMES else value for field, value in values.items() if value is not None}, text)
        for at, source, values, text in noted]


def new_id(source, taken):
    while True:
        id = f"{LETTER[source]}-" + "".join(secrets.choice(LETTERS) for _ in range(6))
        if id not in taken:
            taken.add(id)
            return id


def lines(*data):
    return "".join(json.dumps(one, ensure_ascii=False) + "\n" for one in data).encode()


def write(folder, noted, random, platform, recorder, seed, names, causes, missing=()):
    """Writes what was noted and reads it again as the grader does. Returns the fingerprint of meta.json."""
    taken, entries, raw = set(), [], []
    # In the order of time. What has the same time stays in the order in which it was noted.
    for at, source, values, text in sorted(behind_the_wall(noted, random), key=lambda one: one[0]):
        id = new_id(source, taken)
        entries.append({"id": id, "at": at, "source": source, **values})
        if text is not None:
            raw.append({"id": id, "text": text})
    folder.mkdir(parents=True)
    content = {
        "entries.jsonl": lines(*entries), "raw.jsonl": lines(*raw),
        "missing.json": json.dumps([{"source": source, "from": since, "to": until} for source, since, until in missing]).encode()}
    for name, data in content.items():
        (folder / name).write_bytes(data)
    meta = json.dumps({"files": {name: fingerprint(data) for name, data in content.items()}, "platform": platform, "recorder": recorder, "seed": seed}).encode()
    (folder / "meta.json").write_bytes(meta)
    recording = load(folder, fingerprint(meta))
    if found := leaks.find(recording, names, causes):
        raise Broken(f"the recording gives its answer away: {found[:3]}")
    return fingerprint(meta), recording
