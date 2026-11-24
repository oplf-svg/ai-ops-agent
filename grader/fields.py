"""The words that recordings and answers are made of.

Each value is a number, yes or no, a handle, or a word from a list. What a stranger wrote has no place here: a handle stands
for it, for example e7 for the seventh event.
"""

import re

NONE = "none"
# Numbers in a recording are counts, cents and milliseconds. None of them comes near this.
MOST = 10**12
# How many conditions a search and a claim can have.
CONDITIONS = 3


class Unreadable(ValueError):
    """A field that does not exist, or a value that it cannot have."""


class Word:
    """A text of a fixed form."""

    def __init__(self, form):
        self._form = re.compile(form)

    def fits(self, value):
        return isinstance(value, str) and value != NONE and self._form.fullmatch(value) is not None

    def read(self, written):
        if not self.fits(written):
            raise Unreadable(f"not one of its values: {written[:40]}")
        return written


class Number:
    """A whole number from 0 up."""

    def fits(self, value):
        # In Python, True is a kind of 1. Here it is not.
        return type(value) is int and 0 <= value < MOST

    def read(self, written):
        # There is one way to write each number, so two texts are the same exactly when their numbers are.
        if not re.fullmatch(r"0|[1-9][0-9]{0,11}", written):
            raise Unreadable(f"not a whole number: {written[:40]}")
        return int(written)


class YesNo:
    def fits(self, value):
        return type(value) is bool

    def read(self, written):
        if written not in ("yes", "no"):
            raise Unreadable(f"neither yes nor no: {written[:40]}")
        return written == "yes"


def one_of(*words):
    return Word("|".join(map(re.escape, words)))


EVENT, ORDER, ITEM, PROCESS = (Word(letter + "[1-9][0-9]{0,3}") for letter in "eoip")
# Names that we give ourselves: feeds and shops.
NAME = Word("[a-z][a-z0-9-]{0,30}")
NUMBER, YES_NO = Number(), YesNo()
STATES = ("waiting", "working", "done", "aside")
REASON = one_of(
    "wrong_signature", "wrong_time", "malformed", "too_large", "worker_ended", "not_json", "not_an_object", "type_unknown",
    "not_text", "field_wrong", "order_known", "database_trouble", "step_failed")
# The five characters of PostgreSQL, or what can be said about an error without repeating its text.
ERROR = Word("[0-9A-Z]{5}|timeout|refused|broken|unreadable|other")

# Every field that an entry can have, by its source.
FIELDS = {
    "log": {
        "process": PROCESS, "level": one_of("information", "warning", "error"),
        "what": one_of(
            "stored", "already", "conflict", "not_stored", "refused", "not_ready", "done", "lost_claim", "given_back",
            "set_aside", "failed", "no_database", "other"),
        "feed": NAME, "event": EVENT, "attempt": NUMBER, "state": one_of(*STATES, "not_ours"), "reason": REASON, "error": ERROR,
        "number": NUMBER,
    },
    # A status that is empty means that there was no answer.
    "front": {"feed": NAME, "event": EVENT, "status": NUMBER},
    "row": {
        "table": one_of("inbox", "conflicts", "orders", "totals"), "feed": NAME, "event": EVENT, "shop": NAME, "state": one_of(*STATES),
        "attempts": NUMBER, "deliveries": NUMBER, "reason": REASON, "overdue": YES_NO, "length": NUMBER, "text": YES_NO, "order": ORDER,
        "item": ITEM, "quantity": NUMBER, "cents": NUMBER, "orders": NUMBER,
    },
    "series": {"name": one_of("waiting", "working", "done", "aside", "database_answers", "waits_for_a_lock"), "value": NUMBER},
    # An exit that is empty means that it still ran at the end.
    "process": {"process": PROCESS, "kind": one_of("api", "worker"), "exit": NUMBER},
}

LETTER = {"log": "L", "front": "F", "row": "R", "series": "S", "process": "P"}
SEARCH = "Q"
# Thirty random bits, so that nobody finds one by trying.
_ID = re.compile(f"[{''.join(LETTER.values())}{SEARCH}]-[a-z2-7]{{6}}")


def is_id(text, letter):
    return isinstance(text, str) and _ID.fullmatch(text) is not None and text[0] == letter


def read(source, field, written):
    """A value as it would stand in a recording. Empty is None."""
    kind = FIELDS.get(source, {}).get(field)
    if kind is None:
        raise Unreadable(f"{source} has no {field}")
    return None if written == NONE else kind.read(written)


def read_conditions(source, where):
    """Pairs of a field and a value, all of which have to hold."""
    if not isinstance(where, list) or not 1 <= len(where) <= CONDITIONS:
        raise Unreadable(f"one to {CONDITIONS} conditions")
    found = {}
    for one in where:
        if not isinstance(one, dict) or set(one) != {"field", "value"} or not all(isinstance(text, str) for text in one.values()):
            raise Unreadable("a condition is a field and a value")
        field = one["field"].lower()
        if field in found:
            raise Unreadable(f"two conditions for {field}")
        found[field] = read(source, field, one["value"])
    return frozenset(found.items())
