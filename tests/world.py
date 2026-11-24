"""Small recordings and runs for the tests. They are made up, and nothing in them ever happened."""

import json

from grader.causes import read_table
from grader.grade import Case, grade
from grader.recording import Recording, read_entry
from grader.run import read_run

MODEL = "some-model"
RUNBOOKS = ("send-it-again", "tell-the-shop")

TABLE = """
# Made up for the tests.
ended-after: A worker ended after its work was committed, and before it said so.
  process kind=worker exit=137 say exit
  then row table=inbox event=$e state=done attempts=1 say state
  no log what=done event=$e
ended-before: A worker ended before its work was committed.
  process kind=worker exit=137 say exit
  then row table=inbox event=$e state=done attempts=2 say attempts
counted-twice: The same event was counted twice.
  row table=inbox event=$e say event
  2+ row table=orders event=$e
refused-often: A feed was refused again and again.
  log what=refused feed=$f reason=wrong_signature say reason
  3+ front feed=$f status=401
key-was-made-up: Somebody made up a secret.
  never
key-was-changed: Somebody changed what was signed.
  never
"""


def entry(id, at, source, **values):
    return read_entry(json.dumps({"id": id, "at": at, "source": source, **values}))


# A worker ended. The work for e1 was done, and no line says so. The work for e2 was done and said.
ENDED = (
    entry("S-starts", 0, "series", name="waiting", value=0),
    entry("F-firsta", 100, "front", feed="north-web", event="e1", status=202),
    entry("L-stored", 110, "log", process="p1", level="information", what="stored", feed="north-web", event="e1"),
    entry("F-second", 200, "front", feed="north-web", event="e2", status=202),
    entry("L-storeb", 210, "log", process="p1", level="information", what="stored", feed="north-web", event="e2"),
    entry("L-donebb", 260, "log", process="p2", level="information", what="done", feed="north-web", event="e2", attempt=1),
    entry("P-worker", 300, "process", process="p2", kind="worker", exit=137),
    entry("P-theapi", 4000, "process", process="p1", kind="api"),
    entry("P-nextwo", 4000, "process", process="p3", kind="worker"),
    entry("R-inboxa", 4000, "row", table="inbox", feed="north-web", event="e1", shop="north", state="done", attempts=1, deliveries=1),
    entry("R-inboxb", 4000, "row", table="inbox", feed="north-web", event="e2", shop="north", state="done", attempts=1, deliveries=1),
    entry("R-ordera", 4000, "row", table="orders", shop="north", order="o1", event="e1", item="i1", quantity=1, cents=500),
    entry("R-orderb", 4000, "row", table="orders", shop="north", order="o2", event="e2", item="i1", quantity=2, cents=700),
    entry("R-totals", 4000, "row", table="totals", shop="north", orders=2, cents=1200),
)
RAW = {"L-stored": '{"Message":"north-web evt_1: New"}', "L-donebb": '{"Message":"north-web evt_2: done at attempt 1"}'}


def recording(*entries, missing=(), raw=None):
    return Recording(entries or ENDED, missing, RAW if raw is None and not entries else raw)


def table(text=TABLE):
    return read_table(text)


# Claims, as a model writes them.

def claim(kind, source, evidence, field="none", value="none", **where):
    return {
        "kind": kind, "source": source, "where": [{"field": name, "value": text} for name, text in where.items()], "field": field, "value": value,
        "evidence": evidence}


def says(source, evidence, field, value):
    return claim("is", source, evidence, field, value)


EXIT = says("process", "P-worker", "exit", "137")
DONE = says("row", "R-inboxa", "state", "done")
SILENT = claim("none", "log", "Q-nodone", what="done", event="e1")
RIGHT = (EXIT, DONE, SILENT)


def answer(verdict, *claims, cause="none", value="none", runbook="none"):
    return {"claims": list(claims), "verdict": verdict, "cause": cause, "value": value, "runbook": runbook}


def named(cause="ended-after", claims=RIGHT, runbook="none"):
    return answer("cause", *claims, cause=cause, runbook=runbook)


def valued(value, *claims):
    return answer("answer", *claims, value=value)


NOT_ENOUGH, NOT_IN_DATA = answer("not_enough"), answer("not_in_data")


# What the tools were asked and what they showed.

def call(tool, *shown, input=None, search="", error=False):
    return {"tool": tool, "input": input or {}, "search": search, "shown": list(shown), "error": error}


def search(id, source, *shown, since="none", until="none", error=False, **where):
    asked = {"source": source, "where": [{"field": name, "value": text} for name, text in where.items()], "from": since, "to": until}
    return call("search", *shown, input=asked, search=id, error=error)


CALLS = (call("list_processes", "P-worker", "P-theapi", "P-nextwo"), call("get_row", "R-inboxa"), search("Q-nodone", "log", what="done", event="e1"))


def run_text(answer, calls=CALLS, case="c1", number=1, **changes):
    data = {
        "case": case, "run": number, "model_asked": MODEL, "models_said": [MODEL], "stop_reason": "end_turn", "stopped": False, "calls": list(calls),
        "sent": ["what is the cause?"], "text": answer if isinstance(answer, str) else json.dumps(answer), "cost": 1500}
    return json.dumps(data | changes)


def run(answer, calls=CALLS, in_recording=None, **changes):
    return read_run(run_text(answer, calls, **changes), in_recording or recording())


def graded(answer, calls=CALLS, truth="ended-after", kind="failure", in_recording=None, with_table=None, case="c1", **changes):
    seen = in_recording or recording()
    return grade(Case(case, kind, truth), run(answer, calls, seen, case=case, **changes), seen, with_table or table(), RUNBOOKS)
