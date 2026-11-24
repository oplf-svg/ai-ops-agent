"""Searches a recording for what would give its answer away: words of the tests that made it, and the code of its cause."""

import re

# Words that a real system would not write about itself. The programs say "wrong signature" and "failed", so those are not here.
WORDS = ("doomed", "poison", "poisoned", "forged", "forgery", "crash", "fault", "faults", "sabotage", "mutant", "planted", "pretend", "staged", "honest", "bad")


def _pattern(word):
    # A word of its own, also in evt_bad-3 and in NotBad, but not in "badge" or "default".
    return re.compile(rf"(?<![a-z]){re.escape(word)}(?![a-z])")


def _plain(text):
    # Words that are written together with a capital between them are taken apart.
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).lower()


def find(recording, names, causes):
    """What gives the answer away, as pairs of a place and a word. `names` are those of the files and processes."""
    words = {word: _pattern(word) for word in WORDS}
    codes = {code: re.compile(r"[-_ ]?".join(map(re.escape, code.split("-")))) for code in causes}
    places = [(f"raw {id}", text) for id, text in recording.raw.items()]
    places += [(f"{entry.id} {field}", value) for entry in recording.entries for field, value in entry.values.items() if isinstance(value, str)]
    places += [("a name", name) for name in names]
    return [(place, word) for place, text in places for word, pattern in {**words, **codes}.items() if pattern.search(_plain(text))]
