"""The fixed form of an answer. The model wrote it, so nothing in it is believed before it was checked."""

import dataclasses

from grader import strict
from grader.fields import FIELDS, NONE, NUMBER, Unreadable, read, read_conditions

VERDICTS = {"failure": ("cause", "not_enough"), "question": ("answer", "not_in_data")}
KINDS = ("is", "count", "sum", "none")
ANSWER = ("claims", "verdict", "cause", "value", "runbook")
CLAIM = ("kind", "source", "where", "field", "value", "evidence")
LONGEST, CLAIMS, SHORT = 20_000, 12, 80


class Unusable(ValueError):
    """Not in the fixed form. That is no answer, and it is not the answer "I don't know" either."""


@dataclasses.dataclass(frozen=True)
class Claim:
    kind: str
    source: str
    conditions: frozenset
    field: str
    # As it would stand in a recording, and as it was written.
    value: object
    written: str
    evidence: str


@dataclasses.dataclass(frozen=True)
class Answer:
    verdict: str
    cause: str
    value: str
    claims: tuple
    runbook: str

    @property
    def known(self):
        return self.verdict in ("cause", "answer")


def _texts(data, names):
    if not isinstance(data, dict) or set(data) != set(names):
        raise Unusable("a name too many or too few")
    for name, value in data.items():
        if name in ("claims", "where"):
            if not isinstance(value, list):
                raise Unusable(f"{name} is not a list")
        elif not isinstance(value, str) or len(value) > SHORT:
            raise Unusable(f"{name} is not a short text")
    return data


def _claim(data):
    data = _texts(data, CLAIM)
    # The service that checks the form does not promise the capitals of the words in it.
    kind, source, field = (data[name].lower() for name in ("kind", "source", "field"))
    if kind not in KINDS or source not in FIELDS:
        raise Unusable("a claim of no known kind or source")
    try:
        conditions = frozenset() if kind == "is" and not data["where"] else read_conditions(source, data["where"])
        match kind:
            case "is":
                value = read(source, field, data["value"])
            case "count":
                value = NUMBER.read(data["value"])
            case "sum":
                # Only a number can be added up, and only a number can be 0.
                read(source, field, "0")
                value = NUMBER.read(data["value"])
            case "none":
                value = None
    except Unreadable as problem:
        raise Unusable(f"a claim that cannot be read: {problem}") from None
    if (kind == "is" and conditions) or (kind in ("count", "none") and field != NONE) or (kind == "none" and data["value"] != NONE):
        raise Unusable(f"a claim with more than {kind} needs")
    return Claim(kind, source, conditions, field, value, data["value"], data["evidence"])


def read_answer(text, kind, causes, runbooks):
    """Reads the answer to a failure or to a question, or says why it cannot be used."""
    try:
        data = _texts(strict.loads(text, LONGEST), ANSWER)
    except Unusable:
        raise
    except ValueError as problem:
        raise Unusable(str(problem)) from None
    verdict, cause, runbook = (data[name].lower() for name in ("verdict", "cause", "runbook"))
    if verdict not in VERDICTS[kind] or cause not in (*causes, NONE) or runbook not in (*runbooks, NONE):
        raise Unusable("a word that is not in its list")
    # What the verdict says has to be there, and nothing else.
    if (verdict == "cause") != (cause != NONE) or (verdict == "answer") != (data["value"] != NONE):
        raise Unusable("the verdict and the rest disagree")
    if runbook != NONE and verdict != "cause":
        raise Unusable("a runbook without a cause")
    if len(data["claims"]) > CLAIMS:
        raise Unusable(f"more than {CLAIMS} claims")
    answer = Answer(verdict, cause, data["value"], tuple(map(_claim, data["claims"])), runbook)
    if answer.known and not answer.claims:
        raise Unusable("a cause or a value, and nothing to show for it")
    return answer


def schema(kind, causes, runbooks):
    """The same form as a JSON schema, for the service that holds the model to it. What it cannot say is checked above."""
    text = {"type": "string"}
    fields = sorted({field for of_source in FIELDS.values() for field in of_source})

    def word(words):
        return {"type": "string", "enum": list(words)}

    def whole(**properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

    def many(items):
        return {"type": "array", "items": items}

    claim = whole(
        kind=word(KINDS), source=word(FIELDS), where=many(whole(field=word(fields), value=text)), field=word([*fields, NONE]), value=text,
        evidence=text)
    # The claims come first: first what was found, then what follows from it.
    return whole(
        claims=many(claim), verdict=word(VERDICTS[kind]), cause=word([*causes, NONE] if kind == "failure" else [NONE]),
        value=text, runbook=word([*runbooks, NONE] if kind == "failure" else [NONE]))
