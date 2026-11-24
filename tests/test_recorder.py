"""The parts of the recorder that need no database and no platform. What they write has to be what was seen, and no more."""

import base64
import hashlib
import hmac
import http.server
import json
import pathlib
import random
import re
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest

from grader import Broken
from grader.causes import read_table
from grader.fields import FIELDS, LETTER
from recorder import lines
from recorder.causes import CAUSES
from recorder.database import OVERDUE, Samples, rows
from recorder.front import AGAIN, NOBODY_THERE, Event, Front, Shops, new_id
from recorder.line import Line
from recorder.plan import chosen
from recorder.programs import Clock, Program
from recorder.write import Handles, behind_the_wall, write

ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = read_table((ROOT / "evidence" / "causes.txt").read_text(encoding="utf-8"))


def line(form, level="Information", problem=None, **said):
    """As the platform writes it: one JSON object, and some names of fields with a sign before them."""
    data = {"EventId": 7, "LogLevel": level, "Category": "Platform", "Message": "as it was", "State": said | {"{OriginalFormat}": form}}
    return json.dumps(data | ({"Exception": problem} if problem else {}))


def wait(check, seconds=5.0):
    end = time.monotonic() + seconds
    while not check() and time.monotonic() < end:
        time.sleep(0.005)
    return check()


class Lines(unittest.TestCase):
    def test_29_every_line_that_the_platform_writes(self):
        e = {"Feed": "north-web", "Event": "evt_1"}
        for written, found in {
            line("{Feed} {Event}: {Stored}", Feed="north-web", **{"@event": "evt_1"}, Stored="New"): {"what": "stored", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: {Stored}", Stored="Already", **e): {"what": "already", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: {Stored}", "Warning", Stored="Conflict", **e): {"what": "conflict", "level": "warning", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: not stored", "Error", "Npgsql.NpgsqlException (0x80004005): Exception while reading from stream", **e): {"what": "not_stored", "level": "error", "error": "broken", "feed": "north-web", "event": "evt_1"},
            line("{Feed}: refused {Number} since the last line like this, {Reason}", "Warning", Feed="no such feed", Number=3, Reason="wrong signature"): {"what": "refused", "level": "warning", "feed": "no-such-feed", "number": 3, "reason": "wrong_signature"},
            line("not ready", "Error", "Npgsql.PostgresException (0x80004005): 42P01: relation \"inbox\" does not exist"): {"what": "not_ready", "level": "error", "error": "42P01"},
            line("{Feed} {Event}: done at attempt {Attempt}", Attempt=2, **e): {"what": "done", "attempt": 2, "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: attempt {Attempt} lost its claim and changed nothing", "Warning", Attempt=1, **e): {"what": "lost_claim", "level": "warning", "attempt": 1, "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}", "Error", Attempt=1, State="aside", Reason="missing or wrong: cents", **e): {"what": "given_back", "level": "error", "attempt": 1, "state": "aside", "reason": "field_wrong", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}", "Warning", Attempt=1, State="no longer ours", Reason="trouble with the database: 55P03", **e): {"what": "given_back", "level": "warning", "attempt": 1, "state": "not_ours", "reason": "database_trouble", "error": "55P03", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: set aside after attempt {Attempt}: {Reason}", "Error", Attempt=5, Reason="its worker died or stopped 5 times", **e): {"what": "set_aside", "level": "error", "attempt": 5, "reason": "worker_ended", "feed": "north-web", "event": "evt_1"},
            line("{Feed} {Event}: attempt {Attempt} failed", "Error", "Npgsql.PostgresException (0x80004005): 25P03: terminating connection", Attempt=1, **e): {"what": "failed", "level": "error", "error": "25P03", "attempt": 1, "feed": "north-web", "event": "evt_1"},
            line("the database did not answer", "Error", "Platform.Core.UnreadableException: not text"): {"what": "no_database", "level": "error", "error": "unreadable"},
        }.items():
            self.assertEqual(lines.read(written), {"level": "information"} | found)
        # Each of them is known, and no other.
        self.assertEqual(len(lines.KNOWN), 10)

    def test_29_a_line_that_is_not_known_stays(self):
        self.assertEqual(lines.read(line("BackgroundService failed", "Critical", "Npgsql.PostgresException (0x80004005): 42P01: relation")), {"level": "error", "what": "other", "error": "42P01"})
        self.assertEqual(lines.read(line("something new", "Warning")), {"level": "warning", "what": "other"})
        self.assertEqual(lines.read("Unhandled exception. System.Exception: x"), {"level": "error", "what": "other"})
        self.assertEqual(lines.read("Npgsql.PostgresException (0x80004005): 57P01: terminating"), {"level": "error", "what": "other", "error": "57P01"})
        for text in ("[1]", '{"a": 1}', "7"):
            self.assertEqual(lines.read(text), {"level": "error", "what": "other"})

    def test_29_a_word_that_is_not_known_is_not_passed_over(self):
        e = {"Feed": "north-web", "Event": "evt_1", "Attempt": 1}
        for written in (
                line("not ready", "Loud"), line("{Feed} {Event}: {Stored}", Stored="Lost", **e), line("{Feed}: refused {Number} since the last line like this, {Reason}", Feed="north-web", Number=1, Reason="no time"),
                line("{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}", State="gone", Reason="not text", **e), line("{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}", State="aside", Reason="not text at all", **e),
                line("{Feed} {Event}: attempt {Attempt} ended as {State}: {Reason}", State="aside", Reason="a step failed: 42p01", **e)):
            with self.subTest(written), self.assertRaises(Broken):
                lines.read(written)

    def test_29_what_can_be_said_about_an_error(self):
        for text, word in {
            "Npgsql.PostgresException (0x80004005): 57P01: terminating connection\n   at Npgsql": "57P01",
            "Npgsql.NpgsqlException (0x80004005): Failed to connect to 127.0.0.1:1\n ---> System.Net.Sockets.SocketException (111): Connection refused": "refused",
            "Npgsql.NpgsqlException (0x80004005): Exception while reading from stream\n ---> System.TimeoutException: Timeout during reading attempt": "timeout",
            "Npgsql.NpgsqlException (0x80004005): Exception while reading from stream\n ---> System.IO.EndOfStreamException: Attempted to read past": "broken",
            "Npgsql.NpgsqlException: x\n ---> Npgsql.PostgresException (0x80004005): 57P03: the database system is starting up": "57P03",
            "Platform.Core.UnreadableException: not text": "unreadable", "System.InvalidOperationException: x": "other",
        }.items():
            self.assertEqual(lines.error(text), word, text)


class Wall(unittest.TestCase):
    NOTED = [
        (5, "front", {"feed": "north-web", "event": "evt_x", "status": None}, None),
        (6, "front", {"feed": "south-web", "event": "evt_x", "status": 202}, None),
        (7, "log", {"process": "program-2", "level": "information", "what": "stored", "feed": "north-web", "event": "evt_x"}, '{"Message":"north-web evt_x: New"}'),
        (9, "row", {"table": "orders", "shop": "north", "order": "A-1", "feed": "north-web", "event": "evt_x", "item": "BOX-S", "quantity": 1, "cents": 5}, None),
        (9, "row", {"table": "orders", "shop": "north", "order": "A-1", "feed": "north-app", "event": "evt_y", "item": "BOX-S", "quantity": 1, "cents": 5}, None),
        (9, "row", {"table": "totals", "shop": "north", "orders": 2, "cents": 10}, None),
        (9, "process", {"process": "program-2", "kind": "worker", "exit": None}, None),
        (3, "series", {"name": "waiting", "value": 0}, None),
    ]

    def test_30_a_name_becomes_a_handle(self):
        found = behind_the_wall(self.NOTED, random.Random(1))
        for _, source, values, _ in found:
            for field, value in values.items():
                self.assertTrue(FIELDS[source][field].fits(value), (source, field, value))
        # What a shop chose stands nowhere any more.
        self.assertNotRegex(json.dumps([values for _, _, values, _ in found]), "evt_|A-1|BOX|program")

    def test_30_the_same_name_is_the_same_handle_and_another_feed_is_another_event(self):
        found = [values for _, _, values, _ in behind_the_wall(self.NOTED, random.Random(1))]
        self.assertEqual(found[0]["event"], found[2]["event"])
        self.assertNotEqual(found[0]["event"], found[1]["event"])
        # Each channel of a shop counts its own orders.
        self.assertNotEqual(found[3]["order"], found[4]["order"])
        self.assertEqual(found[3]["item"], found[4]["item"])
        self.assertEqual(found[2]["process"], found[6]["process"])

    def test_30_what_is_empty_is_left_out(self):
        found = [values for _, _, values, _ in behind_the_wall(self.NOTED, random.Random(1))]
        self.assertEqual((set(found[0]), set(found[6])), ({"feed", "event"}, {"process", "kind"}))

    def test_30_a_number_says_nothing_about_what_came_first(self):
        handles = Handles(random.Random(3))
        for number in range(40):
            handles.note("e", number)
        handles.draw()
        drawn = [int(handles.of("e", number)[1:]) for number in range(40)]
        self.assertEqual(sorted(drawn), list(range(1, 41)))
        self.assertNotEqual(drawn, sorted(drawn))


class Written(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name) / "r1"

    def write(self, noted=Wall.NOTED, names=("program-2",), missing=()):
        return write(self.folder, noted, random.Random(1), "9ff662f", "here", 7, names, list(CAUSES), missing)

    def test_30_what_was_noted_is_read_again_by_the_grader(self):
        meta, recording = self.write()
        self.assertEqual([entry.at for entry in recording.entries], [3, 5, 6, 7, 9, 9, 9, 9])
        self.assertEqual([entry.source for entry in recording.entries][:4], ["series", "front", "front", "log"])
        self.assertEqual(list(recording.raw.values()), ['{"Message":"north-web evt_x: New"}'])
        self.assertEqual(recording.by_id[next(iter(recording.raw))].get("what"), "stored")
        self.assertRegex(meta, "^[0-9a-f]{64}$")

    def test_36_what_could_not_be_seen_is_a_gap(self):
        _, recording = self.write(missing=[("row", 0, 9)])
        self.assertEqual((recording.missing, recording.has_gap("row"), recording.has_gap("log")), ((("row", 0, 9),), True, False))

    def test_30_the_ids_are_drawn_anew(self):
        _, one = self.write()
        self.folder = self.folder.parent / "r2"
        _, other = self.write()
        self.assertFalse(set(one.by_id) & set(other.by_id))
        for entry in one.entries:
            self.assertEqual(entry.id[0], LETTER[entry.source])

    def test_22_what_gives_the_answer_away_is_not_written_off_as_a_recording(self):
        noted = [*Wall.NOTED, (4, "log", {"process": "program-2", "level": "error", "what": "other"}, "the doomed one")]
        with self.assertRaisesRegex(Broken, "gives its answer away"):
            self.write(noted)

    def test_22_a_name_of_a_program_can_give_it_away_as_well(self):
        with self.assertRaisesRegex(Broken, "gives its answer away"):
            self.write(names=["worker-ended-before-commit"])


class Api(http.server.ThreadingHTTPServer):
    """Answers as it is told, one after the other. None: it hangs up without an answer."""

    daemon_threads = True

    def __init__(self, *answers, takes=0.01):
        self.answers, self.asked, self.at_once, self.most, self.takes = list(answers), [], 0, 0, takes
        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        server = self.server
        server.at_once += 1
        server.most = max(server.most, server.at_once)
        body = self.rfile.read(int(self.headers["Content-Length"]))
        server.asked.append((self.path, dict(self.headers), body))
        time.sleep(server.takes)
        status = server.answers.pop(0) if server.answers else 202
        server.at_once -= 1
        if status is None:
            self.close_connection = True
            return
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_):
        pass


def nobody():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FrontDoor(unittest.TestCase):
    def api(self, *answers):
        api = Api(*answers)
        self.addCleanup(api.stop)
        return api

    def test_31_what_a_copy_answers(self):
        front = Front()
        front.add(self.api(202, 409, 503).port)
        self.assertEqual([front.send("north-web", {}, b"x") for _ in range(3)], [202, 409, 503])

    def test_31_no_answer_is_not_the_same_as_nobody_there(self):
        front = Front()
        front.add(self.api(None).port)
        self.assertIsNone(front.send("north-web", {}, b"x"))
        front = Front()
        front.add(nobody())
        self.assertEqual(front.send("north-web", {}, b"x"), NOBODY_THERE)

    def test_31_it_goes_round_and_leaves_out_who_is_not_there(self):
        front, there = Front(), self.api()
        front.add(nobody())
        front.add(there.port)
        self.assertEqual([front.send("north-web", {}, b"x") for _ in range(5)], [NOBODY_THERE, 202, 202, 202, 202])
        one, other, front = self.api(), self.api(), Front()
        front.add(one.port)
        front.add(other.port)
        for _ in range(6):
            front.send("north-web", {}, b"x")
        self.assertEqual((len(one.asked), len(other.asked)), (3, 3))

    def test_31_the_last_one_is_asked_again_and_again(self):
        front = Front()
        front.add(nobody())
        self.assertEqual([front.send("north-web", {}, b"x") for _ in range(2)], [NOBODY_THERE, NOBODY_THERE])


class Feed:
    name, secret = "north-web", b"s" * 32


class ShopsSend(unittest.TestCase):
    def shops(self, *answers, make=None, every=(0.01, 0.02), takes=0.01):
        api = Api(*answers, takes=takes)
        self.addCleanup(api.stop)
        front, self.noted, self.trouble = Front(), [], []
        front.add(api.port)
        shops = Shops(front, lambda source, **values: self.noted.append((source, values)), random.Random(1), make or (lambda: Event(Feed, f"evt_{len(self.noted)}", {"n": 1})), self.trouble.append, every, again=(0.01, 0.03))
        self.addCleanup(lambda: setattr(shops, "over", True))
        shops.start()
        return shops, api

    def test_32_it_sends_again_until_it_is_taken(self):
        shops, _ = self.shops(None, 503, 502, 202)
        event = shops.send(Event(Feed, "evt_1", {"n": 1}))
        self.assertTrue(wait(lambda: len(event.answers) == 4 and shops.idle))
        self.assertEqual(event.answers, [None, 503, 502, 202])
        self.assertEqual([values for _, values in self.noted], [{"feed": "north-web", "event": "evt_1", "status": status} for status in event.answers])
        self.assertEqual(set(AGAIN), {None, 502, 503})
        self.assertEqual(shops.events, [event])

    def test_32_what_is_refused_is_not_sent_again(self):
        shops, api = self.shops(401, 409, 500, 413)
        for number in range(4):
            shops.send(Event(Feed, f"evt_{number}", {"n": 1}))
        self.assertTrue(wait(lambda: len(self.noted) == 4))
        time.sleep(0.08)
        self.assertEqual(len(api.asked), 4)

    def test_32_what_should_come_only_once_comes_once(self):
        shops, api = self.shops(None, None)
        shops.send(Event(Feed, "evt_1", {"n": 1}), again=False)
        self.assertTrue(wait(lambda: self.noted))
        time.sleep(0.08)
        self.assertEqual(len(api.asked), 1)

    def test_32_one_request_at_a_time(self):
        # An answer takes longer than it is until the next order, so whoever does not wait is seen.
        shops, api = self.shops(takes=0.08)
        shops.begin()
        self.assertTrue(wait(lambda: len(api.asked) >= 8))
        shops.pause()
        self.assertTrue(wait(lambda: shops.idle))
        self.assertEqual(api.most, 1)
        number = len(api.asked)
        time.sleep(0.08)
        # After the pause nothing comes by itself any more.
        self.assertEqual(len(api.asked), number)

    def test_32_where_it_goes_and_how_it_is_signed(self):
        shops, api = self.shops()
        event = shops.send(Event(Feed, "evt_1", {"n": 1}))
        shops.send(Event(Feed, "evt_2", {"n": 1}), make_headers=lambda: {"webhook-id": "mine"}, name="east-web")
        self.assertTrue(wait(lambda: len(api.asked) == 2))
        (path, headers, body), (other_path, other_headers, _) = api.asked
        self.assertEqual((path, other_path), ("/hooks/north-web", "/hooks/east-web"))
        # As the platform checks it: the id, the time of the header and the body, with dots between them.
        wanted = hmac.new(Feed.secret, b".".join([headers["webhook-id"].encode(), headers["webhook-timestamp"].encode(), event.body]), hashlib.sha256).digest()
        self.assertEqual(headers["webhook-signature"], "v1," + base64.b64encode(wanted).decode())
        self.assertEqual((body, other_headers["webhook-id"]), (b'{"n": 1}', "mine"))
        self.assertTrue(wait(lambda: len(self.noted) == 2))
        self.assertEqual(self.noted[1], ("front", {"feed": "no-such-feed", "event": "evt_2", "status": 202}))

    def test_22_an_id_cannot_be_a_word(self):
        for number in range(200):
            self.assertRegex(new_id(random.Random(number)), r"\Aevt_[0-9]{12}\Z")

    def test_37_trouble_in_the_shops_is_said(self):
        def make():
            raise ValueError("no order today")

        shops, _ = self.shops(make=make)
        shops.begin()
        self.assertTrue(wait(lambda: self.trouble))
        self.assertIn("no order today", self.trouble[0])


class Echo(threading.Thread):
    """Says back what it hears, and remembers it."""

    def __init__(self):
        super().__init__(daemon=True)
        self.heard, self._listener = [], socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                near, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(near,), daemon=True).start()

    def _one(self, near):
        with near:
            while data := near.recv(1000):
                self.heard.append(data)
                try:
                    near.sendall(b"re: " + data)
                except OSError:
                    return


class Cut(unittest.TestCase):
    def ask(self, line, *texts):
        """What comes back on one connection. An empty answer means that it was cut."""
        answers = []
        with socket.create_connection(("127.0.0.1", line.port), 2) as near:
            near.settimeout(2)
            for text in texts:
                try:
                    near.sendall(text)
                    answers.append(near.recv(1000))
                except OSError:
                    answers.append(b"")
        return answers

    def line(self, *times, before=False):
        self.echo = Echo()
        line = Line(self.echo.port, re.compile(rb"COMMIT(?!TED)"), times, before)
        self.addCleanup(line.end)
        return line

    def test_33_after_it_was_done_and_before_the_answer(self):
        line = self.line(2)
        self.assertEqual(self.ask(line, b"COMMIT 1", b"SELECT", b"COMMIT 2"), [b"re: COMMIT 1", b"re: SELECT", b""])
        self.assertEqual(self.echo.heard, [b"COMMIT 1", b"SELECT", b"COMMIT 2"])
        self.assertTrue(wait(lambda: line.cut == 1))
        # Only that one.
        self.assertEqual(self.ask(line, b"COMMIT 3", b"COMMITTED"), [b"re: COMMIT 3", b"re: COMMITTED"])
        self.assertEqual((line.seen, line.cut), (3, 1))

    def test_33_before_it_is_asked(self):
        line = self.line(1, before=True)
        self.assertEqual(self.ask(line, b"COMMIT 1"), [b""])
        self.assertEqual(self.ask(line, b"COMMIT 2"), [b"re: COMMIT 2"])
        self.assertEqual((self.echo.heard, line.cut), ([b"COMMIT 2"], 1))

    def test_33_nobody_at_the_other_end(self):
        line = Line(nobody(), re.compile(b"x"), [1])
        self.addCleanup(line.end)
        began = time.monotonic()
        # It hangs up, and it is still there for the next one.
        self.assertEqual([self.ask(line, b"x"), self.ask(line, b"x")], [[b""], [b""]])
        self.assertLess(time.monotonic() - began, 1.5)


class Running(unittest.TestCase):
    def program(self, code):
        self.heard, clock = [], Clock()
        program = Program("program-1", "worker", [sys.executable, "-u", "-c", code], {}, clock, lambda program, at, text: self.heard.append((program.name, at, text)))
        self.addCleanup(program.finish)
        return program, clock

    def test_34_every_line_with_its_time(self):
        self.program("import time\nprint('one')\nprint()\ntime.sleep(0.2)\nprint('two', flush=True)\nimport sys; sys.stderr.write('three')")
        self.assertTrue(wait(lambda: len(self.heard) == 3))
        self.assertEqual([(name, text) for name, _, text in self.heard], [("program-1", "one"), ("program-1", "two"), ("program-1", "three")])
        self.assertGreaterEqual(self.heard[1][1] - self.heard[0][1], 150)

    def test_34_how_it_ended(self):
        program, clock = self.program("import time; print('here'); time.sleep(60)")
        self.assertTrue(wait(lambda: self.heard))
        self.assertEqual((program.alive, program.exit, program.end), (True, None, None))
        program.send(signal.SIGKILL)
        self.assertTrue(wait(lambda: program.exit is not None))
        self.assertEqual((program.alive, program.exit), (False, 137))
        self.assertLessEqual(program.end, clock.now())
        ended, _ = self.program("raise SystemExit(1)")
        self.assertTrue(wait(lambda: ended.exit is not None))
        self.assertEqual(ended.exit, 1)


class NoAnswer(Exception):
    pass


class NoTable(Exception):
    pass


class Database:
    """A stand-in. What it answers is made up."""

    def __init__(self):
        self.hangs, self.gone, self.empty, self.breaks = threading.Event(), False, False, False
        self.hangs.set()

    def __call__(self):
        if self.gone:
            raise NoAnswer
        return Connection(self)


class Connection:
    def __init__(self, database):
        self.database, self.closed = database, False

    def close(self):
        self.closed = True

    def execute(self, sql):
        self.database.hangs.wait(5)
        if self.database.breaks:
            raise ZeroDivisionError("nobody thought of that")
        # A connection that was lost stays lost.
        if self.database.gone or self.closed:
            self.closed = True
            raise NoAnswer
        if "pg_stat_activity" in sql:
            self.row = (3, 1)
        elif self.database.empty:
            raise NoTable
        else:
            self.row = (4, 2, 9, 0)
        return self

    def fetchone(self):
        return self.row


class Sampled(unittest.TestCase):
    def samples(self, database):
        self.noted, self.trouble = [], []
        samples = Samples(database, Clock(), lambda source, at, **values: self.noted.append((at, values["name"], values["value"])), self.trouble.append, NoAnswer, NoTable, patience=0.05, pause=0.06)
        self.addCleanup(samples.over.set)
        samples.start()

    def last(self, name):
        return next((value for _, one, value in reversed(self.noted) if one == name), None)

    def test_35_what_is_there(self):
        self.samples(Database())
        self.assertTrue(wait(lambda: len(self.noted) >= 14))
        self.assertEqual({name: value for _, name, value in self.noted}, {"database_answers": 1, "waits_for_a_lock": 3, "waits_for_a_standby": 1, "waiting": 4, "working": 2, "done": 9, "aside": 0})

    def test_35_no_answer_in_time_and_then_one(self):
        database = Database()
        self.samples(database)
        self.assertTrue(wait(lambda: self.last("database_answers") == 1))
        database.hangs.clear()
        self.assertTrue(wait(lambda: [value for _, name, value in self.noted if name == "database_answers"][-3:] == [0, 0, 0]))
        database.hangs.set()
        self.assertTrue(wait(lambda: self.last("database_answers") == 1))

    def test_35_nobody_there(self):
        database = Database()
        database.gone = True
        self.samples(database)
        self.assertTrue(wait(lambda: self.last("database_answers") == 0))
        self.assertEqual({name for _, name, _ in self.noted}, {"database_answers"})
        database.gone = False
        self.assertTrue(wait(lambda: self.last("database_answers") == 1))

    def test_35_a_connection_that_was_lost(self):
        database = Database()
        self.samples(database)
        self.assertTrue(wait(lambda: self.last("database_answers") == 1))
        database.gone = True
        self.assertTrue(wait(lambda: self.last("database_answers") == 0))
        database.gone = False
        self.assertTrue(wait(lambda: self.last("database_answers") == 1))

    def test_35_a_table_that_is_missing_is_no_silence(self):
        database = Database()
        database.empty = True
        self.samples(database)
        self.assertTrue(wait(lambda: len(self.noted) >= 6))
        self.assertEqual({name: value for _, name, value in self.noted}, {"database_answers": 1, "waits_for_a_lock": 3, "waits_for_a_standby": 1})

    def test_37_trouble_with_the_samples_is_said(self):
        database = Database()
        database.breaks = True
        self.samples(database)
        self.assertTrue(wait(lambda: self.trouble))
        self.assertIn("nobody thought of that", self.trouble[0])


class Rows(unittest.TestCase):
    class Connection:
        """Answers by the table that is asked for."""

        def __init__(self, tables):
            self.tables, self.asked = tables, []

        def transaction(self):
            self.asked.append("begin")
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.asked.append("end")

        def execute(self, sql, values=None):
            self.asked.append(sql)
            if "to_regclass" in sql:
                self.found = [(values[0].removeprefix("public.") in self.tables,)]
            else:
                found = re.search(r" from (\w+)", sql)
                if found and found[1] not in self.tables:
                    raise NoTable
                self.found = self.tables[found[1]] if found else []
            return self

        def fetchone(self):
            return self.found[0]

        def fetchall(self):
            return self.found

    TABLES = {
        "inbox": [("north-web", "evt_1", "north", "working", 5, 1, None, True, b"{}"), ("north-web", "evt_2", "north", "aside", 1, 2, "not text", True, b"\xff\xfe")],
        "conflicts": [("north-web", "evt_1", 1, b"abc")], "orders": [("north", "A-1", "north-web", "evt_3", "BOX-S", 2, 300)], "totals": [("north", 1, 300)]}

    def test_36_the_rows_of_all_tables(self):
        found, whole = rows(self.Connection(self.TABLES), lines.reason)
        self.assertTrue(whole)
        self.assertEqual(found, [
            {"table": "inbox", "feed": "north-web", "event": "evt_1", "shop": "north", "state": "working", "attempts": 5, "deliveries": 1, "reason": None, "overdue": True, "length": 2, "text": True},
            {"table": "inbox", "feed": "north-web", "event": "evt_2", "shop": "north", "state": "aside", "attempts": 1, "deliveries": 2, "reason": "not_text", "overdue": None, "length": 2, "text": False},
            {"table": "conflicts", "feed": "north-web", "event": "evt_1", "deliveries": 1, "length": 3, "text": True},
            {"table": "orders", "shop": "north", "order": "A-1", "feed": "north-web", "event": "evt_3", "item": "BOX-S", "quantity": 2, "cents": 300},
            {"table": "totals", "shop": "north", "orders": 1, "cents": 300}])

    def test_36_all_of_one_moment(self):
        connection = self.Connection(self.TABLES)
        rows(connection, lines.reason)
        self.assertEqual((connection.asked[0], connection.asked[-1]), ("begin", "end"))
        self.assertIn("repeatable read", connection.asked[1])
        self.assertEqual(sum(OVERDUE in sql for sql in connection.asked), 1)

    def test_36_a_table_that_is_not_there(self):
        found, whole = rows(self.Connection({"orders": self.TABLES["orders"], "totals": self.TABLES["totals"]}), lines.reason)
        self.assertEqual([one["table"] for one in found], ["orders", "totals"])
        # It is said, because nobody can know any more what was in the others.
        self.assertFalse(whole)
        for gone in ("inbox", "conflicts"):
            self.assertFalse(rows(self.Connection({name: some for name, some in self.TABLES.items() if name != gone}), lines.reason)[1], gone)


class Plan(unittest.TestCase):
    def test_38_every_cause_of_the_table_is_recorded(self):
        self.assertEqual(list(CAUSES), list(TABLE.causes))

    def test_38_two_and_two_belong_together(self):
        never = [cause for cause, needs in TABLE._needs.items() if needs is None]
        self.assertEqual([cause.code for cause in CAUSES.values() if cause.pair], never)
        self.assertEqual([CAUSES[code].pair for code in never], [number for number in range(1, 11) for _ in range(2)])

    def test_38_four_parts_are_everything_once(self):
        parts = [task for number in range(1, 5) for task in chosen([f"{number}/4"])]
        self.assertEqual(len(parts), len(set(parts)))
        self.assertEqual(set(parts), {(code, seed) for code, cause in CAUSES.items() for seed in range(1, 9 if cause.pair else 5)})
        # Each cause is made in one part only, so its version is built once.
        for number in range(1, 5):
            for other in range(1, number):
                self.assertFalse({code for code, _ in chosen([f"{number}/4"])} & {code for code, _ in chosen([f"{other}/4"])})

    def test_38_two_that_look_the_same_are_made_in_the_same_place(self):
        for number in range(1, 5):
            tasks = chosen([f"{number}/4"])
            for code, seed in tasks:
                if pair := CAUSES[code].pair:
                    # One after the other, so that nothing else can be the difference.
                    twins = [one for one in tasks if CAUSES[one[0]].pair == pair and one[1] == seed]
                    self.assertEqual(len(twins), 2)
                    self.assertEqual(tasks.index(twins[1]) - tasks.index(twins[0]), 1)

    def test_38_a_sample_is_each_cause_once(self):
        self.assertEqual(chosen(["sample"]), [(code, 1) for code in CAUSES])
        self.assertEqual(chosen(["table-missing", "body-too-large"]), [("table-missing", 1), ("body-too-large", 1)])
        for words in (["table-mising"], [], ["5/"]):
            with self.assertRaises(SystemExit):
                chosen(words)

    def test_38_the_platform_stands_at_one_commit(self):
        self.assertRegex((ROOT / "webhook-platform.commit").read_text(encoding="utf-8"), r"\A[0-9a-f]{40}\n\Z")
