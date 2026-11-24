"""One run of the platform with its shops. A cause is a function that gets a scene and lets one thing go wrong in it."""

import base64
import contextlib
import json
import os
import pathlib
import random
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request

import psycopg

from grader import Broken
from recorder import lines
from recorder import build  # noqa: F401  (puts the platform's own tools on the path)
from recorder.database import Samples, rows
from recorder.front import Event, Front, Shops, new_id
from recorder.programs import Clock, Program
from recorder.settings import FEEDS, ITEMS, SETTINGS
from world import Postgres, free_port, is_stopped, wait_until


class Feed:
    def __init__(self, name, shop):
        self.name, self.shop, self.secret = name, shop, secrets.token_bytes(32)

    def written(self):
        return "whsec_" + base64.b64encode(self.secret).decode()


class Scene:
    def __init__(self, folder, version, seed, net=True):
        self.random, self.version, self.net = random.Random(seed), version, net
        self.folder, self.clock = pathlib.Path(folder), Clock()
        self._noted, self._lock, self._frozen = [], threading.Lock(), False
        # What went wrong in another thread. Nothing that happens there may go unnoticed.
        self.problems = []
        self.programs, self.facts = [], {}
        self.feeds = [Feed(*one) for one in FEEDS]
        self._feeds_on = list(self.feeds)
        self.postgres = Postgres()
        self._faults = self.folder / "faults"
        self._faults.mkdir(parents=True)

    # What is noted

    def note(self, source, at=None, text=None, **values):
        with self._lock:
            if not self._frozen:
                self._noted.append((self.clock.now() if at is None else at, source, values, text))

    def _heard(self, program, at, text):
        try:
            self.note("log", at=at, text=text, process=program.name, **lines.read(text))
        except Broken as problem:
            self.problems.append(str(problem))

    def said(self, **values):
        """What the programs said, as the fields of the lines."""
        with self._lock:
            return [one for _, source, one, _ in self._noted if source == "log" and values.items() <= one.items()]

    def last_lines(self, program, number=4):
        """For whoever looks why there is no recording."""
        with self._lock:
            mine = [text for _, source, one, text in self._noted if source == "log" and one["process"] == program.name]
        return [f"{program.name} ({program.kind}, exit {program.exit}): {text[:400]}" for text in mine[-number:]]

    def sampled(self, name, least):
        with self._lock:
            return [one["value"] for _, source, one, _ in self._noted if source == "series" and one["name"] == name and one["value"] >= least]

    # Before

    def begin(self):
        self.postgres.start()
        self.database = f"shop_{secrets.token_hex(4)}"
        self.password = secrets.token_hex(16)
        with self.postgres.connect() as admin:
            admin.execute(f"create role {self.database} login password '{self.password}'")
            admin.execute(f"create database {self.database} owner {self.database}")
        self._feeds_file = self.folder / "feeds.json"
        self._feeds_file.touch(mode=0o600)
        self._feeds_file.write_text(json.dumps({"feeds": [{"name": feed.name, "shop": feed.shop, "secrets": [feed.written()]} for feed in self.feeds]}), encoding="utf-8")
        made = subprocess.run(self._command("worker", "migrate"), env=self._environment(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        if made.returncode:
            raise Broken(f"no tables: {made.stdout[-400:]}")
        if not self.net:
            self.ask("alter table orders drop constraint orders_once")
        self.front = Front()
        self.shops = Shops(self.front, self.note, self.random, self._usual, self.problems.append)
        self.samples = Samples(lambda: self.postgres.connect(self.database), self.clock, self.note, self.problems.append, psycopg.Error, psycopg.errors.UndefinedTable)
        self.nobody_there = free_port()

    def _command(self, kind, *words):
        return ["dotnet", str(self.version.programs / kind / f"Platform.{kind.capitalize()}.dll"), *words]

    def _environment(self, faults=(), port=None, line=None):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PLATFORM_")} | SETTINGS | {
            "PLATFORM_DATABASE": self.postgres.dotnet(self.database, self.database, self.password, line and line.port),
            "PLATFORM_FEEDS": str(self._feeds_file), "PLATFORM_FAULT": ",".join(faults), "PLATFORM_FAULTS": str(self._faults), "DOTNET_gcServer": "0"}
        if self.version.statements:
            environment["PLATFORM_SQL"] = str(self.version.statements)
        if port:
            environment["ASPNETCORE_URLS"] = f"http://127.0.0.1:{port}"
        return environment

    def _start(self, kind, faults, port=None, line=None):
        program = Program(f"program-{len(self.programs) + 1}", kind, self._command(kind), self._environment(faults, port, line), self.clock, self._heard)
        self.programs.append(program)
        return program

    def worker(self, *faults, line=None):
        return self._start("worker", faults, line=line)

    def api(self, *faults, line=None):
        port = free_port()
        program = self._start("api", faults, port, line)
        wait_until("a copy of the API is ready", lambda: self._is_ready(port) or not program.alive, 60)
        if not program.alive:
            raise Broken("a copy of the API did not start")
        self.front.add(port)
        self.front.look_after(port)
        return program

    @staticmethod
    def _is_ready(port):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=2) as answer:
                return answer.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def open(self, apis=None, workers=None):
        """From here on it is recorded: the copies are there, the shops begin to send."""
        for make in apis or (self.api, self.api):
            make()
        for make in workers or (self.worker, self.worker):
            make()
        time.sleep(1)
        with self._lock:
            self._noted.clear()
            self.clock.begin()
        self.samples.start()
        self.shops.start()
        self.shops.begin()

    # What shops send

    def order(self, feed=None, item=None, id=None, cents=None, **changed):
        feed = feed or self.random.choice(self._feeds_on)
        data = {
            "type": "order.placed", "order": f"A-{self.random.randrange(10**7, 10**8)}", "sku": item or self.random.choice(ITEMS), "quantity": self.random.randint(1, 5),
            "cents": cents or self.random.randint(100, 20_000), "placed_at": "2026-11-24T10:00:00Z"} | changed
        return Event(feed, id or new_id(self.random), {name: value for name, value in data.items() if value is not None})

    def _usual(self):
        return self.order()

    def only(self, *feeds):
        """Only these feeds go on by themselves."""
        self._feeds_on = list(feeds)

    def feed(self, shop=None):
        return self.random.choice([feed for feed in self.feeds if shop in (None, feed.shop)])

    # What the recorder knows, and no recording has

    def ask(self, sql, *values):
        with self.postgres.connect(self.database) as connection:
            cursor = connection.execute(sql, values or None)
            return cursor.fetchall() if cursor.description else []

    def one(self, sql, *values):
        return self.ask(sql, *values)[0][0]

    def reached(self, point, action):
        """The programs that came to this place and were told to do that."""
        found = []
        for program in self.programs:
            path = self._faults / str(program.pid)
            if path.exists() and f"{point} {action}" in path.read_text(encoding="utf-8").split("\n"):
                found.append(program)
        return found

    def wait(self, what, check, seconds=40.0):
        def looked():
            self.no_problems()
            return check()

        return wait_until(what, looked, seconds, 0.2)

    def no_problems(self):
        if self.problems:
            raise Broken(f"something else went wrong: {self.problems[:3]}")

    def wait_for_stop(self, program, seconds=40.0):
        self.wait("a program stands still", lambda: is_stopped(program.pid), seconds)

    def sleep(self, least, most=None):
        time.sleep(self.random.uniform(least, least if most is None else most))

    def fact(self, what, true):
        """What has to be so that the recording shows what it should. Otherwise there is no recording."""
        self.facts[what] = bool(true)
        if not true:
            raise Broken(f"it did not happen: {what}")

    # After

    def settle(self, stuck=0, seconds=90.0):
        """No new orders. Waits until everything is done but so many events."""
        self.shops.pause()
        self.wait("the shops have sent everything", lambda: self.shops.idle, seconds)
        self.wait("everything is settled", lambda: self.one("select count(*) from inbox where state in ('waiting', 'working')") <= stuck, seconds)
        self.sleep(0.7, 1.5)

    def close(self):
        """The end of the recording: the rows, and how the programs stand. Returns what was noted, and what could not be seen."""
        self.shops.pause()
        with self.postgres.connect(self.database) as connection:
            last, whole = rows(connection, lines.reason)
        end = self.clock.now()
        self.no_problems()
        with self._lock:
            self._frozen = True
            for values in last:
                self._noted.append((end, "row", values, None))
            for program in self.programs:
                ended = program.exit is not None
                self._noted.append((program.end if ended else end, "process", {"process": program.name, "kind": program.kind, "exit": program.exit if ended else None}, None))
            # Of a table that is gone nobody can say any more that something was not in it.
            return list(self._noted), [] if whole else [("row", 0, end)]

    def finish(self):
        self._frozen = True
        if hasattr(self, "samples"):
            self.samples.over.set()
        if hasattr(self, "shops"):
            self.shops.over = True
            self.front.over.set()
        for program in self.programs:
            with contextlib.suppress(Exception):
                program.finish()
        with contextlib.suppress(Exception):
            self.postgres.remove()
