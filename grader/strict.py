"""JSON that can be read in one way only."""

import json


def _once(pairs):
    found = dict(pairs)
    if len(found) != len(pairs):
        raise ValueError("a name stands twice")
    return found


def _no(text):
    raise ValueError(f"not a whole number: {text[:20]}")


def loads(text, most):
    """No name stands twice, no number is anything but whole, and it has at most so many characters."""
    if len(text) > most:
        raise ValueError(f"longer than {most} characters")
    try:
        return json.loads(text, object_pairs_hook=_once, parse_float=_no, parse_constant=_no)
    except RecursionError:
        raise ValueError("too deep") from None
