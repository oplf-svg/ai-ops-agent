"""Whether two causes can be told apart by anything that was recorded.

A case "without enough evidence" is worth something only if really nobody can know. So two different causes are made, each
recorded several times. If anything about the one is always larger, earlier or more often than about the other, they can be told
apart, and the pair is thrown out.
"""

import collections
import itertools
import re

from grader import Broken
from grader.fields import EVENT, FIELDS, ITEM, NUMBER, ORDER, PROCESS

# With eight of each, one thing that is only chance separates them in one of 6435 pairs. Three to five hundred different things are
# looked at, so about one pair in fifty is thrown out by chance. It is recorded again then, with other seeds.
EACH = 8
_HANDLES = (EVENT, ITEM, ORDER, PROCESS)
# Numbers that say what something is, and not how much.
_CODES = ("status", "exit")


def _shapes(entry):
    """What kinds of entry it is: every choice of its words, so not its id, its time, its numbers, and which event or process it was.
    All words together are not enough. The feed is drawn, so a difference is spread over the feeds, and no single one shows it."""
    kinds = FIELDS[entry.source]
    words = sorted((field, value) for field, value in entry.values.items() if field in _CODES or kinds[field] is not NUMBER and kinds[field] not in _HANDLES)
    for size in range(len(words) + 1):
        for some in itertools.combinations(words, size):
            yield entry.source, some


def _pauses(entries, field):
    """How long it took until the same one came again."""
    last, found = {}, []
    for entry in entries:
        one = entry.get(field)
        if one in last:
            found.append(entry.at - last[one])
        last[one] = entry.at
    return found


def _first_of_each_event(entries):
    found = {}
    for entry in entries:
        if entry.get("event") is not None:
            found.setdefault(entry.get("event"), entry.at)
    return found


def features(recording):
    """Everything about a recording that can be put into a number."""
    by_shape, end = collections.defaultdict(list), max(entry.at for entry in recording.entries)
    for entry in recording.entries:
        for shape in _shapes(entry):
            by_shape[shape].append(entry)
    found = {("gaps", source): sum(one == source for one, _, _ in recording.missing) for source in FIELDS}
    for shape, entries in by_shape.items():
        found["how many", shape] = len(entries)
        found["the first", shape], found["the last", shape] = entries[0].at, entries[-1].at
        found["before the end", shape] = end - entries[-1].at
        for field, kind in FIELDS[shape[0]].items():
            some = [entry for entry in entries if entry.get(field) is not None]
            values = [entry.get(field) for entry in some]
            if values and kind is NUMBER:
                found["least", shape, field], found["most", shape, field], found["sum", shape, field] = min(values), max(values), sum(values)
            elif values and kind in _HANDLES:
                found["different ones", shape, field] = len(set(values))
                found["of the same", shape, field] = max(collections.Counter(values).values())
                if pauses := _pauses(some, field):
                    found["soonest again", shape, field], found["latest again", shape, field] = min(pauses), max(pauses)
    events = {shape: _first_of_each_event(entries) for shape, entries in by_shape.items() if len(shape[1]) == 1}
    for one, other in itertools.permutations(events, 2):
        found["before", one, other] = int(by_shape[one][0].at < by_shape[other][0].at)
        # And of the same event: how many have the one and not the other, and how long it is from the one to the other.
        found["without", one, other] = len(events[one].keys() - events[other].keys())
        if both := events[one].keys() & events[other].keys():
            waits = [events[other][event] - events[one][event] for event in both]
            found["soonest after", one, other], found["latest after", one, other] = min(waits), max(waits)
    for word, number in collections.Counter(word for text in recording.raw.values() for word in set(re.findall("[A-Za-z_]+", text))).items():
        found["lines with", word] = number
    return found


def tells_apart(these, those):
    """What tells the recordings of the one cause from those of the other. Nothing means that nobody can know."""
    if len(these) < EACH or len(those) < EACH:
        raise Broken(f"a pair needs {EACH} recordings of each cause")
    these, those = [features(one) for one in these], [features(one) for one in those]
    found = []
    for feature in sorted(set().union(*these, *those), key=repr):
        ones, others = [of.get(feature, -1) for of in these], [of.get(feature, -1) for of in those]
        if max(ones) < min(others) or max(others) < min(ones):
            found.append(feature)
    return found
