"""Which causes are recorded how often, and which part of it somebody does."""

import collections
import re

from grader.pairs import EACH
from recorder.causes import CAUSES

# Two that look the same are compared by so many of each. The others are recorded so often that chance shows itself.
OFTEN = {True: EACH, False: 4}


def together():
    """Two that should look the same belong to one part, one after the other. Another computer would be a difference by itself."""
    found = collections.defaultdict(list)
    for code, cause in CAUSES.items():
        found[cause.pair or code].append(code)
    return list(found.values())


def chosen(words):
    """Causes and their seeds. "sample" is each cause once, "2/4" the second of four parts of all, and otherwise they are named."""
    if words == ["sample"]:
        return [(code, 1) for code in CAUSES]
    if len(words) == 1 and (part := re.fullmatch(r"([1-9])/([1-9])", words[0])):
        number, of = int(part[1]), int(part[2])
        # All of a cause in one part, so that each version is built in one part only.
        return [(code, seed) for codes in together()[number - 1::of] for seed in range(1, OFTEN[len(codes) > 1] + 1) for code in codes]
    if not words or (unknown := set(words) - set(CAUSES)):
        raise SystemExit(f"not known: {', '.join(sorted(unknown)) if words else 'nothing was asked for'}")
    return [(code, 1) for code in words]
