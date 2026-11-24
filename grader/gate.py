"""The gate: whether what an answer relies on exists, was seen in this run, and is true. It knows nothing of any cause."""

# The steps, in their order. An answer is caught at the first one that it does not pass.
EXISTS, SEEN, TRUE, VALUE, ENOUGH = "an id that does not exist", "not seen in this run", "not true", "a value that no claim has", "not enough for this cause"


class Caught(Exception):
    """The answer does not go out. "I don't know" goes out instead."""

    def __init__(self, step, why):
        super().__init__(f"{step}: {why}")
        self.step = step


def _exists(claim, run, recording):
    there = claim.evidence in (recording.by_id if claim.kind == "is" else run.searches)
    if not there:
        raise Caught(EXISTS, claim.evidence)


def _seen(claim, run):
    """An entry has to be shown by a tool. A number or an absence has to rest on a search that asked for exactly that."""
    if claim.kind == "is":
        if claim.evidence not in run.shown:
            raise Caught(SEEN, claim.evidence)
        return
    search = run.searches[claim.evidence]
    if search.source != claim.source or search.conditions != claim.conditions:
        raise Caught(SEEN, f"{claim.evidence} was another search")
    if not search.whole:
        raise Caught(SEEN, f"{claim.evidence} looked at a part of the time")


def _true(claim, recording):
    """Every claim is run again, on the whole recording and not on what was shown of it."""
    if claim.kind == "is":
        entry = recording.by_id[claim.evidence]
        if entry.source != claim.source or entry.get(claim.field) != claim.value:
            raise Caught(TRUE, f"{claim.evidence}: {claim.field} is not {claim.written}")
        return
    if recording.has_gap(claim.source):
        raise Caught(TRUE, f"{claim.source} was not recorded all the time")
    found = recording.matching(claim.source, claim.conditions)
    match claim.kind:
        case "count":
            right = len(found) == claim.value
        case "sum":
            values = [entry.get(claim.field) for entry in found]
            right = bool(values) and None not in values and sum(values) == claim.value
        case "none":
            right = not found
    if not right:
        raise Caught(TRUE, f"{claim.kind} in {claim.source} is not right")


def check(answer, run, recording):
    """Raises Caught at the first step that the answer does not pass. All of its claims count, whatever it concludes."""
    for claim in answer.claims:
        _exists(claim, run, recording)
    for claim in answer.claims:
        _seen(claim, run)
    for claim in answer.claims:
        _true(claim, recording)
    # There is one way to write each value, so the same text is the same value.
    if answer.verdict == "answer" and answer.value not in {claim.written for claim in answer.claims}:
        raise Caught(VALUE, answer.value)
