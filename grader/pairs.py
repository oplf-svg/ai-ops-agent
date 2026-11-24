"""Whether two causes can be told apart by anything that was recorded.

A case "without enough evidence" is worth something only if really nobody can know. So two different causes are made, each
recorded several times. If anything about the one is always larger, earlier or more often than about the other, they can be told
apart, and the pair is thrown out.
"""

import collections

from grader import Broken
from grader.fields import EVENT, FIELDS, ITEM, NUMBER, ORDER, PROCESS

# With eight of each, one thing that is only chance separates them in one of 6435 pairs.
EACH = 8
_HANDLES = (EVENT, ITEM, ORDER, PROCESS)


def _shape(entry):
    """What kind of entry it is: everything but its id, its time, its numbers, and which event or process it was."""
    kinds = FIELDS[entry.source]
    words = sorted((field, value) for field, value in entry.values.items() if kinds[field] is not NUMBER and kinds[field] not in _HANDLES)
    return entry.source, tuple(words), tuple(sorted(entry.values.keys()))


def features(recording):
    """Everything about a recording that can be put into a number."""
    by_shape = collections.defaultdict(list)
    for entry in recording.entries:
        by_shape[_shape(entry)].append(entry)
    found = {("gaps", source): sum(one == source for one, _, _ in recording.missing) for source in FIELDS}
    for shape, entries in by_shape.items():
        kinds = FIELDS[shape[0]]
        found["how many", shape] = len(entries)
        found["the first", shape], found["the last", shape] = entries[0].at, entries[-1].at
        for field in shape[2]:
            values = [entry.get(field) for entry in entries]
            if kinds[field] is NUMBER:
                found["least", shape, field], found["most", shape, field], found["sum", shape, field] = min(values), max(values), sum(values)
            elif kinds[field] in _HANDLES:
                found["different ones", shape, field] = len(set(values))
                found["of the same", shape, field] = max(collections.Counter(values).values())
    for one in by_shape:
        for other in by_shape:
            if one != other:
                found["before", one, other] = int(by_shape[one][0].at < by_shape[other][0].at)
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
