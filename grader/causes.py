"""The table of causes: which ones there are, and what has to be shown before one of them may be named.

The table is written by a person, in evidence/causes.txt. Each cause is one line, and below it stands what it needs:

    kettle-boiled-dry: The kettle was on, and there was no water in it.
      process kind=worker exit=137 say exit
      then row table=inbox event=$e state=done|aside say state
      no log what=done event=$e
      3+ log what=failed event=$e

A line is an entry that has to be shown, with the fields that have to be said about it. `no` means that nothing like it may be
there, `3+` that there have to be so many of them, and `then` that it comes after the entry of the line before. What starts with
$ has to be the same in all lines of the cause, and done|aside is one of the two. A cause that nothing recorded can prove has the
one line `never`.
"""

import collections
import dataclasses
import re

from grader import Broken
from grader.fields import FIELDS, NONE, Unreadable, read

_CODE = re.compile("[a-z][a-z0-9-]{2,60}")
_SAME = re.compile(r"\$[a-z]")
_MANY = re.compile(r"([2-9]|[1-9][0-9])\+")


@dataclasses.dataclass(frozen=True)
class Same:
    """The same value in all lines of a cause."""

    name: str


@dataclasses.dataclass(frozen=True)
class OneOf:
    """Any of these values."""

    values: frozenset


@dataclasses.dataclass(frozen=True)
class Need:
    kind: str
    source: str
    where: tuple
    say: frozenset = frozenset()
    then: bool = False
    many: int = 0


class Cited:
    """What an answer can lean on: the entries of its claims with what was said about them, and its numbers and absences.

    The gate has found all of its claims to be true.
    """

    def __init__(self, claims, recording):
        self._recording = recording
        self._said = collections.defaultdict(set)
        for claim in claims:
            if claim.kind == "is":
                self._said[claim.evidence].add(claim.field)
        self._absent = [(claim.source, claim.conditions) for claim in claims if claim.kind == "none"]
        self._counted = [(claim.source, claim.conditions, claim.value) for claim in claims if claim.kind == "count"]

    def entries(self, need):
        return [entry for entry in self._recording.entries if entry.id in self._said and entry.source == need.source and need.say <= self._said[entry.id]]

    def nothing(self, source, conditions):
        """If there is nothing at all of some kind, then there is nothing of a narrower kind either."""
        return any(where == source and fewer <= conditions for where, fewer in self._absent)

    def many(self, source, conditions, number):
        """If there are so many of a narrower kind, then there are at least as many of the wider one."""
        if any(where == source and more >= conditions and value >= number for where, more, value in self._counted):
            return True
        return sum(self._recording.by_id[id].source == source and self._recording.by_id[id].fits(conditions) for id in self._said) >= number


class Everything:
    """As if an answer had shown the whole recording. Says what could be shown at all."""

    def __init__(self, recording):
        self._recording = recording

    def entries(self, need):
        return [entry for entry in self._recording.entries if entry.source == need.source]

    def nothing(self, source, conditions):
        return not self._recording.has_gap(source) and not self._recording.matching(source, conditions)

    def many(self, source, conditions, number):
        return len(self._recording.matching(source, conditions)) >= number


def _bind(where, entry, bound):
    """The values that stand for the same everywhere, with those of this entry. None if it does not fit."""
    bound = dict(bound)
    for field, value in where:
        real = entry.get(field)
        if isinstance(value, Same):
            if real is None or bound.setdefault(value.name, real) != real:
                return None
        elif isinstance(value, OneOf):
            if real not in value.values:
                return None
        elif real != value:
            return None
    return bound


def _met(needs, shown, bound, used, last):
    """Whether the needs can be met, each line by an entry of its own."""
    if not needs:
        return True
    need, rest = needs[0], needs[1:]
    if need.kind == "entry":
        for entry in shown.entries(need):
            if entry.id in used or (need.then and entry.at < last):
                continue
            now = _bind(need.where, entry, bound)
            if now is not None and _met(rest, shown, now, used | {entry.id}, entry.at):
                return True
        return False
    conditions = frozenset((field, bound[value.name] if isinstance(value, Same) else value) for field, value in need.where)
    there = shown.nothing(need.source, conditions) if need.kind == "no" else shown.many(need.source, conditions, need.many)
    return there and _met(rest, shown, bound, used, last)


class Table:
    def __init__(self, needs, sentences):
        self._needs, self.sentences = needs, sentences

    @property
    def causes(self):
        return tuple(self._needs)

    @property
    def open(self):
        """The causes for which nobody has written yet what they need."""
        return tuple(cause for cause, needs in self._needs.items() if needs == [])

    def complete(self):
        if self.open:
            raise Broken(f"the table does not say yet what these need: {', '.join(self.open)}")

    def supports(self, cause, claims, recording):
        """Whether these claims, all of them true, are enough for the cause."""
        return self._fits(cause, Cited(claims, recording))

    def possible(self, recording):
        """Every cause that could be shown from this recording, whoever looks. It should be the true one and no other."""
        return {cause for cause in self._needs if self._fits(cause, Everything(recording))}

    def _fits(self, cause, shown):
        needs = self._needs[cause]
        # None: nothing can prove it. Empty: nobody has said yet what would.
        return bool(needs) and _met(needs, shown, {}, frozenset(), 0)


def _need(words):
    kind, many, then = "entry", 0, words[0] == "then"
    if then:
        words = words[1:]
    if words and words[0] == "no":
        kind, words = "no", words[1:]
    elif words and (found := _MANY.fullmatch(words[0])):
        kind, many, words = "many", int(found[1]), words[1:]
    if not words or words[0] not in FIELDS:
        raise Broken("a line needs a source")
    source, words, say = words[0], words[1:], frozenset()
    if "say" in words:
        at = words.index("say")
        if len(words) != at + 2:
            raise Broken("one list of fields comes after say, and nothing after that")
        say, words = frozenset(words[at + 1].split(",")), words[:at]
    where = {}
    for word in words:
        field, sign, value = word.partition("=")
        if not sign or field in where:
            raise Broken(f"not a field and a value: {word}")
        if _SAME.fullmatch(value):
            if field not in FIELDS[source]:
                raise Broken(f"{source} has no {field}")
            where[field] = Same(value[1:])
        else:
            try:
                values = [read(source, field, one) for one in value.split("|")]
            except Unreadable as problem:
                raise Broken(str(problem)) from None
            where[field] = values[0] if len(values) == 1 else OneOf(frozenset(values))
    if not where:
        raise Broken("a line needs at least one field and its value")
    if kind != "entry" and (then or say or any(isinstance(value, OneOf) for value in where.values())):
        raise Broken("then, say and one of several values belong to an entry")
    if kind == "entry" and (not say or not say <= where.keys()):
        raise Broken("what has to be said about an entry are some of the fields of its line")
    return Need(kind, source, tuple(where.items()), say, then, many)


def _check(needs):
    """A cause leans on something that is there, and what stands for the same has been seen before it is used elsewhere."""
    if not any(need.kind != "no" for need in needs):
        raise Broken("a cause cannot lean only on what is not there")
    known = {}
    for need in needs:
        for field, value in need.where:
            if not isinstance(value, Same):
                continue
            if need.kind != "entry" and value.name not in known:
                raise Broken(f"${value.name} has to stand in an entry first")
            if known.setdefault(value.name, FIELDS[need.source][field]) is not FIELDS[need.source][field]:
                raise Broken(f"${value.name} stands for two kinds of things")
    if needs[0].then:
        raise Broken("then needs a line before")


def read_table(text):
    """Reads the table. A cause without any line is allowed, but the table is then not complete."""
    needs, sentences, cause = {}, {}, None
    for number, line in enumerate(text.split("\n"), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            if not line.startswith(" "):
                cause, sign, sentence = line.partition(":")
                if not sign or not _CODE.fullmatch(cause) or cause == NONE or cause in needs or not sentence.strip():
                    raise Broken("a cause is a code of its own and a sentence")
                needs[cause], sentences[cause] = [], sentence.strip()
                continue
            if cause is None:
                raise Broken("a line without a cause")
            words = line.split()
            if words == ["never"]:
                if needs[cause] != []:
                    raise Broken("never stands alone")
                needs[cause] = None
                continue
            if needs[cause] is None:
                raise Broken("never stands alone")
            needs[cause].append(_need(words))
        except Broken as problem:
            raise Broken(f"line {number}: {problem}") from None
    for cause, lines in needs.items():
        if lines:
            try:
                _check(lines)
            except Broken as problem:
                raise Broken(f"{cause}: {problem}") from None
    return Table(needs, sentences)
