"""What the platform wrote, as the fields of an entry.

A line that is not known becomes "other" and stays in the recording. A known line with a word that is not known is an error: then the
platform has changed, and this file has to change with it.
"""

import json
import re

from grader import Broken

LEVELS = {"Information": "information", "Warning": "warning", "Error": "error", "Critical": "error"}
STORED = {"New": "stored", "Already": "already", "Conflict": "conflict"}
STATES = {"waiting": "waiting", "aside": "aside", "no longer ours": "not_ours"}
REFUSED = {"wrong signature": "wrong_signature", "wrong time": "wrong_time", "malformed": "malformed", "too large": "too_large"}
REASONS = {
    "not JSON, or a name in it stands twice": "not_json", "not an object": "not_an_object", "not a type that is known": "type_unknown", "not text": "not_text",
    "the order is already there": "order_known", "trouble with the database": "database_trouble", "a step failed": "step_failed"}
# A name that does not exist is not repeated by the platform, and not here either.
NO_FEED = "no-such-feed"
# The text of a line without what it says about the one case.
KNOWN = {
    "{Feed} {Event}: {Stored}": None,
    "{Feed} {Event}: not stored": "not_stored",
    "{Feed}: refused {Number} since the last line like this, {Reason}": "refused",
    "not ready": "not_ready",
    "{Feed} {Event}: done at attempt {Attempt}": "done",
    "{Feed} {Event}: attempt {Attempt} lost its claim and changed nothing": "lost_claim",
    "{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}": "given_back",
    "{Feed} {Event}: set aside after attempt {Attempt}: {Reason}": "set_aside",
    "{Feed} {Event}: attempt {Attempt} failed": "failed",
    "the database did not answer": "no_database",
}
_CODE = re.compile(r"PostgresException[^:]{0,40}: ([0-9A-Z]{5}): ")


def error(text):
    """What can be said about an error without repeating its text."""
    if found := _CODE.search(text):
        return found[1]
    if "UnreadableException" in text:
        return "unreadable"
    if "ConnectionRefused" in text or "Connection refused" in text or "SocketException (111)" in text:
        return "refused"
    if "TimeoutException" in text or "timed out" in text:
        return "timeout"
    return "broken" if "NpgsqlException" in text or "EndOfStreamException" in text else "other"


def reason(text):
    """The reason of an event, as a word and the code that stands behind it."""
    if re.fullmatch(r"its worker died or stopped [1-9][0-9]* times", text):
        return "worker_ended", None
    if text.startswith("missing or wrong: "):
        return "field_wrong", None
    words, _, code = text.partition(": ")
    if words not in REASONS or (code and not re.fullmatch("[0-9A-Z]{5}", code)):
        raise Broken(f"a reason that is not known: {text[:60]}")
    return REASONS[words], code or None


def _one(words, value):
    if value not in words:
        raise Broken(f"a word that is not known: {str(value)[:60]}")
    return words[value]


def read(text):
    """The fields of the line. The event is still the id that the shop chose."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict) or "LogLevel" not in data:
        # Not a line of the log, for example the last words of a process.
        code = error(text)
        return {"level": "error", "what": "other"} | ({"error": code} if code != "other" else {})
    said = {name.lstrip("@").lower(): value for name, value in (data.get("State") or {}).items()}
    form, problem = said.get("{originalformat}"), data.get("Exception")
    found = {"level": _one(LEVELS, data["LogLevel"])}
    if form not in KNOWN:
        return found | {"what": "other"} | ({"error": error(problem)} if problem else {})
    found["what"] = KNOWN[form] or _one(STORED, said["stored"])
    if problem:
        found["error"] = error(problem)
    for name in ("feed", "event", "attempt", "number"):
        if name in said:
            found[name] = said[name]
    if found.get("feed") == "no such feed":
        found["feed"] = NO_FEED
    if "state" in said:
        found["state"] = _one(STATES, said["state"])
    if "reason" in said:
        if found["what"] == "refused":
            found["reason"] = _one(REFUSED, said["reason"])
        else:
            found["reason"], code = reason(said["reason"])
            if code:
                found["error"] = code
    return found
