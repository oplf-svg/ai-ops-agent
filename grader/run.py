"""A run: one try at one case by one model, as the harness wrote it down. The harness is ours, but it can be wrong."""

import dataclasses

from grader import Broken, strict
from grader.fields import FIELDS, NONE, SEARCH, Unreadable, is_id, read_conditions

# All that the agent can do. A test fails if there is one more.
TOOLS = ("search", "get_history", "get_row", "get_series", "list_processes")
RUN = {"case", "run", "model_asked", "models_said", "stop_reason", "stopped", "calls", "sent", "text", "cost"}
CALL = {"tool", "input", "search", "shown", "error"}
# How a run can end. Whatever else comes is a mistake of the harness.
ENDS = {"end_turn": "", "refusal": "refused", "max_tokens": "cut_off", "model_context_window_exceeded": "cut_off", "tool_use": "ran_out"}


@dataclasses.dataclass(frozen=True)
class Search:
    source: str
    conditions: frozenset
    # A search with a window of time says nothing about the rest.
    whole: bool


@dataclasses.dataclass(frozen=True)
class Run:
    case: str
    number: int
    model: str
    # Empty if it ended with an answer.
    apart: str
    text: str
    shown: frozenset
    searches: dict
    # The names of tools that it tried and that do not exist.
    acts: tuple
    sent: tuple
    # In millionths of a dollar.
    cost: int


def _need(right, what):
    if not right:
        raise Broken(f"a run that is not right: {what}")


def _search(data):
    _need(isinstance(data, dict) and set(data) == {"source", "where", "from", "to"} and isinstance(data["source"], str), "a search")
    _need(data["source"] in FIELDS, "a search in no source")
    try:
        conditions = read_conditions(data["source"], data["where"])
    except Unreadable as problem:
        raise Broken(f"a run that is not right: a search that was answered and cannot be read: {problem}") from None
    return Search(data["source"], conditions, data["from"] == data["to"] == NONE)


def read_run(text, recording):
    """Reads what the harness wrote, and checks it against the recording."""
    try:
        data = strict.loads(text, 20_000_000)
    except ValueError as problem:
        raise Broken(f"a run that is not right: {problem}") from None
    _need(isinstance(data, dict) and set(data) == RUN, "a name too many or too few")
    for name in ("case", "model_asked", "stop_reason", "text"):
        _need(isinstance(data[name], str), name)
    for name in ("models_said", "sent"):
        _need(isinstance(data[name], list) and all(isinstance(one, str) for one in data[name]), name)
    _need(type(data["run"]) is int and data["run"] > 0 and type(data["cost"]) is int and data["cost"] >= 0 and type(data["stopped"]) is bool, "a number")
    _need(isinstance(data["calls"], list), "calls")
    _need(data["stopped"] or data["stop_reason"] in ENDS, f"it ended in a way that is not known: {data['stop_reason'][:20]}")
    # A stop before the first reply leaves nobody who could have said a name.
    _need(data["stopped"] or data["models_said"], "nobody replied")
    _need(all(model == data["model_asked"] for model in data["models_said"]), "another model replied")

    shown, searches, acts = set(), {}, []
    for call in data["calls"]:
        _need(isinstance(call, dict) and set(call) == CALL and isinstance(call["tool"], str) and type(call["error"]) is bool and isinstance(call["shown"], list), "a call")
        if call["tool"] not in TOOLS:
            acts.append(call["tool"])
            _need(call["error"], "a tool that does not exist has answered")
        if call["error"]:
            # What an error says was not found by anybody.
            continue
        for id in call["shown"]:
            _need(isinstance(id, str) and id in recording.by_id, "a tool showed what is not in the recording")
        shown.update(call["shown"])
        if call["tool"] == "search":
            _need(is_id(call["search"], SEARCH) and call["search"] not in searches, "a search without an id of its own")
            searches[call["search"]] = _search(call["input"])
    return Run(
        data["case"], data["run"], data["model_asked"], "stopped" if data["stopped"] else ENDS[data["stop_reason"]], data["text"],
        frozenset(shown), searches, tuple(acts), tuple(data["sent"]), data["cost"])
