"""What can be seen of the database: samples while the programs run, and the rows at the end."""

import threading
import time

WAITS = """
select count(*) filter (where wait_event_type = 'Lock'), count(*) filter (where wait_event = 'SyncRep')
  from pg_stat_activity where datname = current_database() and application_name in ('api', 'worker')
"""
STATES = """
select count(*) filter (where state = 'waiting'), count(*) filter (where state = 'working'), count(*) filter (where state = 'done'), count(*) filter (where state = 'aside')
  from inbox
"""
# Over for so long that somebody must have seen it.
OVERDUE = "interval '5 seconds'"


class Samples(threading.Thread):
    """Asks the database twice a second. The one who asks can be kept waiting, so somebody else looks at the clock."""

    def __init__(self, connect, clock, note, trouble, no_answer, no_table, patience=0.45, pause=0.5):
        super().__init__(daemon=True)
        # How long an answer may take to count as one, and how often it is asked.
        self._patience, self._pause = patience, pause
        self._connect, self._clock, self._note, self._trouble, self._no_answer, self._no_table = connect, clock, note, trouble, no_answer, no_table
        self._wanted, self._answered = threading.Event(), threading.Event()
        self._answer, self._asking, self.over = None, False, threading.Event()
        threading.Thread(target=self._ask, daemon=True).start()

    def _ask(self):
        connection = None
        while True:
            self._wanted.wait()
            self._wanted.clear()
            answer = None
            try:
                connection = connection or self._connect()
                answer = dict(zip(("waits_for_a_lock", "waits_for_a_standby"), connection.execute(WAITS).fetchone()))
                try:
                    answer |= zip(("waiting", "working", "done", "aside"), connection.execute(STATES).fetchone())
                except self._no_table:
                    # It answers. There is only nothing to count.
                    pass
            except self._no_answer:
                if connection:
                    connection.close()
                connection = None
            except Exception as problem:
                self._trouble(f"the samples: {problem!r}")
            self._answer = answer
            self._answered.set()

    def run(self):
        due = time.monotonic()
        while not self.over.is_set():
            at = self._clock.now()
            if not self._asking:
                self._asking = True
                self._answered.clear()
                self._wanted.set()
            answer = None
            if self._answered.wait(self._patience):
                self._asking, answer = False, self._answer
            if not self.over.is_set():
                self._note("series", at=at, name="database_answers", value=0 if answer is None else 1)
                for name, value in (answer or {}).items():
                    self._note("series", at=at, name=name, value=value)
            due += self._pause
            self.over.wait(max(0.0, due - time.monotonic()))


def is_text(body):
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _there(connection, table):
    return connection.execute("select to_regclass(%s) is not null", (f"public.{table}",)).fetchone()[0]


def rows(connection, read_reason):
    """All rows of one moment, so that no order is seen without what belongs to it."""
    found = []
    with connection.transaction():
        connection.execute("set transaction isolation level repeatable read read only")
        if _there(connection, "inbox"):
            for feed, event, shop, state, attempts, deliveries, reason, overdue, body in connection.execute(
                    f"select feed, event_id, shop, state, attempts, deliveries, reason, due_at < now() - {OVERDUE}, body from inbox order by feed, event_id").fetchall():
                found.append({
                    "table": "inbox", "feed": feed, "event": event, "shop": shop, "state": state, "attempts": attempts, "deliveries": deliveries,
                    "reason": read_reason(reason)[0] if reason else None, "overdue": overdue if state in ("waiting", "working") else None, "length": len(body), "text": is_text(bytes(body))})
        if _there(connection, "conflicts"):
            for feed, event, deliveries, body in connection.execute("select feed, event_id, deliveries, body from conflicts order by feed, event_id").fetchall():
                found.append({"table": "conflicts", "feed": feed, "event": event, "deliveries": deliveries, "length": len(body), "text": is_text(bytes(body))})
        for shop, number, feed, event, sku, quantity, cents in connection.execute("select shop, number, feed, event_id, sku, quantity, cents from orders order by shop, feed, number").fetchall():
            found.append({"table": "orders", "shop": shop, "order": number, "feed": feed, "event": event, "item": sku, "quantity": quantity, "cents": cents})
        for shop, orders, cents in connection.execute("select shop, orders, cents from totals order by shop").fetchall():
            found.append({"table": "totals", "shop": shop, "orders": orders, "cents": cents})
    return found
