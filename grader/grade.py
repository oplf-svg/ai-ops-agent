"""Grades one run: what the answer was, whether it may go out, and whether it is right."""

import dataclasses

from grader import Broken, strict
from grader.answer import VERDICTS, Answer, Unusable, read_answer
from grader.fields import NONE
from grader.gate import ENOUGH, Caught, check
from grader.recording import fingerprint

# What an answer can come to.
JUDGED = ("right", "false", "gave_up", "caught")
# What is no answer. None of these is ever right, wrong or "I don't know".
APART = ("broken", "refused", "cut_off", "ran_out", "stopped")
DONT_KNOW = ("dont_know", NONE, NONE, NONE)


@dataclasses.dataclass(frozen=True)
class Case:
    """A question about a recording, and the truth. The truth is kept where no tool can read it."""

    id: str
    kind: str
    # The code of the cause, or the value. "none" if nobody can know it from the recording.
    truth: str

    @property
    def knowable(self):
        return self.truth != NONE


@dataclasses.dataclass(frozen=True)
class Result:
    case: Case
    run: int
    model: str
    # With all steps, and with those of the gate alone: as if nobody had said what a cause needs.
    outcome: str
    bare: str
    # Where it was caught.
    step: str
    # What went out, and what the model itself wrote.
    decision: tuple
    answer: Answer | None
    acts: tuple
    cost: int


def read_case(id, content, expected):
    """Reads the truth of a case. It has to be the one that was counted."""
    if fingerprint(content) != expected:
        raise Broken(f"{id}: the truth has changed")
    try:
        data = strict.loads(content.decode("utf-8"), 2_000)
    except ValueError as problem:
        raise Broken(f"{id}: {problem}") from None
    if not isinstance(data, dict) or set(data) != {"kind", "truth"} or not isinstance(data["truth"], str) or data["kind"] not in VERDICTS:
        raise Broken(f"{id}: a truth is a kind and a value")
    return Case(id, data["kind"], data["truth"])


def judge(case, answer):
    """Whether it is right, by the truth alone."""
    if not answer.known:
        return "gave_up" if case.knowable else "right"
    said = answer.cause if case.kind == "failure" else answer.value
    return "right" if said == case.truth else "false"


def grade(case, run, recording, table, runbooks):
    if run.case != case.id:
        raise Broken(f"a run of {run.case} for {case.id}")
    if case.kind == "failure" and case.knowable:
        if case.truth not in table.causes:
            raise Broken(f"{case.id}: its cause is not in the table")
        # Another cause for which nobody has written anything is never let through, so it does not matter here.
        if case.truth in table.open:
            raise Broken(f"{case.id}: nobody has written yet what {case.truth} needs")

    def result(outcome, bare="", step="", decision=DONT_KNOW, answer=None):
        return Result(case, run.number, run.model, outcome, bare or outcome, step, decision, answer, run.acts, run.cost)

    if run.apart:
        return result(run.apart)
    try:
        answer = read_answer(run.text, case.kind, table.causes, runbooks)
    except Unusable:
        return result("broken")
    try:
        check(answer, run, recording)
    except Caught as problem:
        return result("caught", step=problem.step, answer=answer)
    bare = judge(case, answer)
    if answer.verdict == "cause" and not table.supports(answer.cause, answer.claims, recording):
        return result("caught", bare, ENOUGH, answer=answer)
    decision = (answer.verdict, answer.cause, answer.value, answer.runbook) if answer.known else DONT_KNOW
    return result(bare, decision=decision, answer=answer)


def check_table(table, failures):
    """What the table gets wrong about pairs of a case and its recording, if somebody showed all that there is.

    If nothing is wrong, then no wrong cause can go out for these recordings, whatever a model writes. That can only be said of a
    complete table.
    """
    table.complete()
    found = []
    for case, recording in failures:
        possible, right = table.possible(recording), {case.truth} if case.knowable else set()
        found += [f"{case.id}: {cause} could be shown as well" for cause in sorted(possible - right)]
        found += [f"{case.id}: {cause} cannot be shown" for cause in sorted(right - possible)]
    return found
