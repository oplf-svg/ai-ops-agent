"""One function for each cause. It opens a scene, lets one thing go wrong in it, and waits until that can be seen.

Each says at its end what has to be true in the world itself. If it is not, there is no recording.
"""

import base64
import dataclasses
import re
import socket
import time

from recorder.front import Event, new_id, signed
from recorder.line import Line
from recorder.settings import BODY, ITEMS, LEASE

COMMIT, STORE = re.compile(rb"COMMIT(?!TED)"), re.compile(rb"event_id")


@dataclasses.dataclass(frozen=True)
class Cause:
    code: str
    play: object
    # One of the platform's own deliberate mistakes, or None.
    mistake: str | None
    # Without the platform's safety net, so that a mistake of the inbox can be seen.
    net: bool
    # Of two causes that should look the same. Nobody can know which one it was.
    pair: int


CAUSES = {}


def cause(code, mistake=None, net=True, pair=0):
    def keep(play):
        CAUSES[code] = Cause(code, play, mistake, net, pair)
        return play

    return keep


# Something outside of the program

@cause("body-too-large")
def body_too_large(s):
    s.open()
    s.sleep(3, 6)
    feed = s.feed()
    for _ in range(s.random.randint(1, 4)):
        small = s.order(feed)
        s.shops.send(Event(feed, small.id, small.body + b" " * (BODY + s.random.randint(1, 4000))), again=False)
        s.sleep(0.3, 1)
    s.sleep(1, 3)
    s.settle()
    s.fact("a body was too large", s.said(what="refused", reason="too_large"))


@cause("feed-unknown")
def feed_unknown(s):
    s.open()
    s.sleep(3, 6)
    name = f"{s.random.choice(['east', 'west', 'main'])}-{s.random.choice(['web', 'app', 'till'])}"
    for _ in range(s.random.randint(1, 4)):
        s.shops.send(s.order(), name=name, again=False)
        s.sleep(0.3, 1)
    s.sleep(1, 3)
    s.settle()
    s.fact("nobody knows the feed", s.said(what="refused", feed="no-such-feed"))


def _api_ends(s, point, then):
    s.open(apis=(s.api, lambda: s.api(f"{point}:kill:{s.random.randint(3, 7)}")))
    other = s.programs[1]
    s.wait("a copy of the API has ended", lambda: not other.alive)
    s.sleep(2, 4)
    s.settle()
    s.fact("it ended there", s.reached(point, "kill") == [other] and other.exit == 137)
    under_way = [event for event in s.shops.events if event.answers[0] is None]
    s.fact("one request was under way, and what came of it", len(under_way) == 1 and under_way[0].answers[-1] == then)


@cause("api-ended-before-storing")
def api_ended_before_storing(s):
    _api_ends(s, "api.after_verify", 202)


@cause("api-ended-after-storing")
def api_ended_after_storing(s):
    _api_ends(s, "api.after_store", 200)


def _said_so(s, but=0):
    """Whoever is killed can take the last line of its log along. Then something would look as if nobody had said it."""
    s.fact("what is done was said, but for so many", s.one("select count(*) from inbox where state = 'done'") == len(s.said(what="done")) + but)


def _worker_ends(s, point):
    """Opens the scene with a worker that is killed at this place, and starts another one soon after."""
    s.open(workers=(lambda: s.worker(f"{point}:kill:{s.random.randint(2, 5)}"), s.worker))
    ended = s.programs[2]
    s.wait("a worker has ended", lambda: not ended.alive)
    s.wait("its end is noted", lambda: ended.exit is not None)
    s.fact("it ended there", s.reached(point, "kill") == [ended] and ended.exit == 137)
    return ended


@cause("worker-ended-before-commit")
def worker_ended_before_commit(s):
    _worker_ends(s, s.random.choice(["worker.after_claim", "worker.after_mark", "worker.after_effect"]))
    s.sleep(0.5, 1.5)
    s.worker()
    s.sleep(2, 4)
    s.settle()
    s.fact("it was done at the second attempt", s.one("select count(*) from inbox where state = 'done' and attempts = 2") == 1)
    _said_so(s)


@cause("worker-ended-after-commit")
def worker_ended_after_commit(s):
    _worker_ends(s, "worker.after_commit")
    s.sleep(0.5, 1.5)
    s.worker()
    s.sleep(2, 4)
    s.settle()
    s.fact("it was done at the first attempt", s.one("select count(*) from inbox where attempts > 1 or state <> 'done'") == 0)
    _said_so(s, but=1)


def _stands_still(s, point):
    """A worker stands still at this place until another one has done its event."""
    s.open(workers=(lambda: s.worker(f"{point}:stop:{s.random.randint(2, 5)}"), s.worker))
    still = s.programs[2]
    s.wait("a worker stands still", lambda: s.reached(point, "stop") == [still])
    s.wait_for_stop(still)
    s.wait("another one has done it", lambda: s.one("select count(*) from inbox where state = 'done' and attempts = 2") == 1, LEASE + 20)
    s.sleep(0.5, 2)
    still.go_on()
    return still


@cause("worker-paused-past-claim")
def worker_paused_past_claim(s):
    still = _stands_still(s, "worker.after_claim")
    s.wait("it notices", lambda: s.said(what="lost_claim"))
    s.sleep(0.5, 2)
    s.settle()
    s.fact("it went on", still.alive and len(s.said(what="lost_claim")) == 1)


@cause("transaction-ended-by-database")
def transaction_ended_by_database(s):
    still = _stands_still(s, "worker.after_mark")
    s.wait("it hears of it", lambda: s.said(what="failed", process=still.name))
    s.sleep(0.5, 2)
    s.settle()
    heard = [one.get("error") for one in s.said(what="failed", process=still.name)]
    s.fact(f"the database said why: {heard}", heard == ["25P03"])


def _ends_every_worker(s, over):
    """An event that ends every worker that reads it. Whoever ended is replaced soon after."""
    item = f"MUG-{s.random.randint(3, 9)}"
    assert item not in ITEMS

    def worker():
        return s.worker(f"worker.read.{item}:kill:1")

    s.open(workers=(worker, worker))
    s.sleep(2, 4)
    event = s.shops.send(s.order(item=item))
    replaced, end = 0, time.monotonic() + 6 * LEASE + 40
    while not over(event):
        if sum(program.exit == 137 for program in s.programs) > replaced:
            s.sleep(0.3, 1)
            worker()
            replaced += 1
        if time.monotonic() > end:
            s.fact(f"it was over in time, after {replaced} ends", False)
        s.sleep(0.2)
    return event


def _state(s, event, what):
    return (s.ask(f"select {what} from inbox where feed = %s and event_id = %s", *event.key) or [[None]])[0][0]


@cause("event-kills-its-worker")
def event_kills_its_worker(s):
    event = _ends_every_worker(s, lambda event: _state(s, event, "state") == "aside")
    s.wait("it is said", lambda: s.said(what="set_aside"))
    s.settle()
    s.fact("five times", _state(s, event, "attempts") == 5 == sum(program.exit == 137 for program in s.programs))
    _said_so(s)


@cause("commit-answer-lost")
def commit_answer_lost(s):
    times = s.random.sample(range(2, 9), s.random.randint(1, 3))
    lines = []

    def worker():
        lines.append(Line(s.postgres.port, COMMIT, times))
        return s.worker(line=lines[0])

    s.open(workers=(worker, s.worker))
    s.wait("the answers are lost", lambda: lines[0].cut == len(times), 60)
    s.sleep(1, 3)
    s.settle()
    s.fact("so often it was not its own any more", len(s.said(what="given_back", state="not_ours")) == len(times))
    s.fact("each was done once", s.one("select count(*) from inbox where state <> 'done' or attempts <> 1") == 0)


@cause("store-answer-lost")
def store_answer_lost(s):
    times = s.random.sample(range(2, 8), s.random.randint(1, 3))
    lines = []

    def api():
        lines.append(Line(s.postgres.port, STORE, times))
        return s.api(line=lines[0])

    s.open(apis=(s.api, api))
    s.wait("the answers are lost", lambda: lines[0].cut == len(times), 60)
    s.sleep(1, 3)
    s.settle()
    # What comes again can lose its answer again. It was stored the first time, so it ends with 200.
    hit = [event.answers for event in s.shops.events if 503 in event.answers]
    s.fact("so often it was there already", sum(answers.count(503) for answers in hit) == len(times) and all(answers[-1] == 200 for answers in hit))


@cause("connections-ended")
def connections_ended(s):
    s.open()
    s.sleep(3, 5)
    for _ in range(s.random.randint(8, 14)):
        s.ask("select pg_terminate_backend(pid) from (select pid from pg_stat_activity where datname = current_database() and application_name in ('api', 'worker') order by random() limit %s) chosen", s.random.randint(1, 2))
        s.sleep(0.25, 0.6)
    s.sleep(1, 2)
    s.settle()
    s.fact("somebody heard it", len(s.said(error="57P01")) >= 2)


@cause("database-restarted")
def database_restarted(s):
    s.open()
    s.sleep(3, 5)
    s.postgres.kill()
    s.sleep(0.8, 1.8)
    s.postgres.start_again()
    s.sleep(2, 3)
    s.settle()
    s.fact("somebody was refused", s.said(error="refused") or s.said(error="57P03"))


@cause("database-hung")
def database_hung(s):
    s.open()
    s.sleep(3, 5)
    s.postgres.hang()
    try:
        # Longer than anybody waits for an answer, and shorter than a claim.
        s.sleep(10, 10.8)
    finally:
        s.postgres.go_on()
    s.sleep(2, 3)
    s.settle()
    s.fact("somebody waited in vain", s.said(error="timeout"))


def _row_is_held(s, until):
    """Somebody else holds the total of one shop, until that has been seen."""
    s.open()
    feed = s.feed()
    s.wait("the shop has a total", lambda: s.one("select count(*) from totals where shop = %s", feed.shop) == 1)
    s.only(*[one for one in s.feeds if one.shop != feed.shop])
    s.sleep(2, 3)
    with s.postgres.connect(s.database) as connection, connection.transaction():
        connection.execute("select 1 from totals where shop = %s for update", (feed.shop,))
        event = s.shops.send(s.order(feed))
        s.wait("it is seen", lambda: until(event), 60)
    s.only(*s.feeds)
    return event


@cause("row-held-by-somebody")
def row_held_by_somebody(s):
    often = s.random.randint(2, 4)
    event = _row_is_held(s, lambda event: len(s.said(what="failed", event=event.id, error="55P03")) >= often)
    s.sleep(1, 3)
    s.settle()
    s.fact("it was done in the end", _state(s, event, "state") == "done")


@cause("standby-missing")
def standby_missing(s):
    s.open()
    s.sleep(3, 5)
    with s.postgres.without_its_standby():
        s.sleep(12, 15)
    s.sleep(2, 3)
    s.settle()
    s.fact("commits waited", len(s.sampled("waits_for_a_standby", 1)) >= 4)
    s.fact("the database answered", 0 not in s.sampled("database_answers", 0))


def _is_missing(s, sql, code):
    s.open()
    s.sleep(3, 5)
    s.ask(sql.format(user=s.database))
    workers = [program for program in s.programs if program.kind == "worker"]
    s.wait("the workers have ended", lambda: all(program.exit is not None for program in workers))
    s.sleep(2, 4)
    s.shops.pause()
    s.wait("the shops have sent everything", lambda: s.shops.idle)
    s.sleep(0.5, 1)
    s.fact("they said why, and that it is their end", [program.exit for program in workers] == [1, 1] and s.said(error=code))


@cause("table-missing")
def table_missing(s):
    _is_missing(s, "drop table conflicts, inbox", "42P01")


@cause("right-missing")
def right_missing(s):
    _is_missing(s, "revoke all on inbox from {user}", "42501")


def _nobody_understands(s, make, ends="aside"):
    s.open()
    s.sleep(3, 5)
    feed = s.feed()
    for _ in range(s.random.randint(1, 4)):
        s.shops.send(make(feed))
        s.sleep(0.3, 1)
    s.sleep(1, 2)
    s.settle()
    s.fact("that is how it ended", s.one("select count(*) from inbox where state = %s and not exists (select from orders where (orders.feed, orders.event_id) = (inbox.feed, inbox.event_id))", ends) >= 1)


def _field_wrong(s, feed):
    return s.order(feed, **s.random.choice([{"sku": None}, {"quantity": 0}, {"quantity": "two"}, {"cents": -5}, {"order": ""}, {"placed_at": "yesterday"}]))


@cause("event-type-unknown")
def event_type_unknown(s):
    kind = s.random.choice(["order.changed", "order.cancelled", "stock.counted"])
    _nobody_understands(s, lambda feed: s.order(feed, type=kind))
    s.fact("that is why", s.said(what="given_back", reason="type_unknown"))


@cause("event-field-wrong")
def event_field_wrong(s):
    _nobody_understands(s, lambda feed: _field_wrong(s, feed))
    s.fact("that is why", s.said(what="given_back", reason="field_wrong"))


# A mistake in the program

@cause("effect-before-mark", "work.effect_before_the_mark")
def effect_before_mark(s):
    _worker_ends(s, "worker.after_effect")
    s.sleep(0.3, 0.8)
    s.worker()
    # It has to end before the claim is over, because then somebody would make the effect once more.
    s.settle(stuck=1, seconds=7)
    s.fact("an order without its mark", s.one("select count(*) from inbox join orders using (feed, event_id) where state = 'working'") == 1)
    _said_so(s)


@cause("mark-before-effect", "work.mark_before_the_effect")
def mark_before_effect(s):
    _worker_ends(s, "worker.after_mark")
    s.sleep(0.5, 1.5)
    s.worker()
    s.sleep(2, 4)
    s.settle()
    s.fact("a mark without its order", s.one("select count(*) from inbox where state = 'done' and not exists (select from orders where (orders.feed, orders.event_id) = (inbox.feed, inbox.event_id))") == 1)
    _said_so(s, but=1)


@cause("trouble-counted", "work.trouble_counts")
def trouble_counted(s):
    event = _row_is_held(s, lambda event: _state(s, event, "state") == "aside")
    s.sleep(1, 2)
    s.settle()
    s.fact("set aside for it", _state(s, event, "state") == "aside" and _state(s, event, "attempts") == 5)


@cause("used-up-never-set-aside", "set_aside.never")
def used_up_never_set_aside(s):
    event = _ends_every_worker(s, lambda event: _state(s, event, "attempts = 5 and due_at < now() - interval '7 seconds'"))
    s.settle(stuck=1)
    s.fact("it still stands there", _state(s, event, "state") == "working" and any(program.kind == "worker" and program.alive for program in s.programs))
    _said_so(s)


def _another_body(s):
    s.open()
    s.sleep(2, 4)
    for _ in range(s.random.randint(1, 3)):
        event = s.shops.send(s.order())
        s.wait("it is there", lambda event=event: event.answers and event.answers[-1] in (200, 202))
        s.sleep(0.5, 1.5)
        s.shops.send(Event(event.feed, event.id, s.order(event.feed).data), again=False)
        s.sleep(0.5, 1)
    s.sleep(1, 2)
    s.settle()
    s.fact("it was said", s.said(what="conflict"))


@cause("conflict-not-kept", "store.forgets_the_other")
def conflict_not_kept(s):
    _another_body(s)
    s.fact("it was not kept", s.one("select count(*) from conflicts") == 0)


@cause("yes-without-database", "receive.yes_without_a_database")
def yes_without_database(s):
    times = s.random.sample(range(2, 8), s.random.randint(1, 3))
    lines = []

    def api():
        lines.append(Line(s.postgres.port, STORE, times, before=True))
        return s.api(line=lines[0])

    s.open(apis=(s.api, api))
    s.wait("the line is cut", lambda: lines[0].cut == len(times), 60)
    s.sleep(1, 3)
    s.settle()
    there = {tuple(row) for row in s.ask("select feed, event_id from inbox")}
    s.fact("a yes, and nothing there", sum(event.answers == [202] and event.key not in there for event in s.shops.events) == len(times))


@cause("unreadable-dropped", "work.drops_the_unreadable")
def unreadable_dropped(s):
    _nobody_understands(s, lambda feed: s.random.choice([_field_wrong(s, feed), s.order(feed, type="order.changed")]), ends="done")


@cause("total-not-added", "effect.forgets_the_sum")
def total_not_added(s):
    s.open()
    s.wait("each shop has three orders", lambda: len(s.ask("select shop from orders group by shop having count(*) >= 3")) == 2, 60)
    s.sleep(2, 5)
    s.settle()
    s.fact("a total is too small", s.one("select count(*) from totals where cents < (select sum(cents) from orders where orders.shop = totals.shop)") == 2)


@cause("mistake-waited-out", "work.everything_is_trouble")
def mistake_waited_out(s):
    s.open()
    s.sleep(3, 5)
    s.ask("drop table conflicts, inbox")
    s.wait("it is waited out", lambda: len(s.said(what="no_database", error="42P01")) >= 4)
    s.sleep(2, 4)
    s.shops.pause()
    s.sleep(1, 2)
    s.fact("nobody ended", all(program.alive for program in s.programs))


@cause("aside-not-said", "work.aside_in_silence")
def aside_not_said(s):
    event = _ends_every_worker(s, lambda event: _state(s, event, "state") == "aside")
    s.sleep(2, 3)
    s.settle()
    s.fact("nobody said it", _state(s, event, "state") == "aside" and not s.said(what="set_aside"))
    _said_so(s)


# Two and two that should look the same

def _refused(s, make, status):
    """Somebody sends what is refused. `make` gives the event and the headers for it."""
    s.open()
    s.sleep(3, 6)
    feed, sent = s.feed(), []
    for _ in range(s.random.randint(1, 4)):
        event, headers = make(feed)
        sent.append(s.shops.send(event, headers, again=False))
        s.sleep(0.3, 1)
    s.sleep(1, 3)
    s.settle()
    s.fact("it was refused", all(event.answers == [status] for event in sent))


@cause("secret-made-up", pair=1)
def secret_made_up(s):
    def make(feed):
        event, secret = s.order(feed), bytes(s.random.getrandbits(8) for _ in range(32))
        return event, lambda: signed(secret, event.id, event.body)

    _refused(s, make, 401)


@cause("body-changed-on-the-way", pair=1)
def body_changed_on_the_way(s):
    def make(feed):
        event, other = s.order(feed), s.order(feed)
        return event, lambda: signed(feed.secret, event.id, other.body)

    _refused(s, make, 401)


@cause("secret-of-another-feed", pair=2)
def secret_of_another_feed(s):
    def make(feed):
        event, other = s.order(feed), next(one for one in s.feeds if one is not feed)
        return event, lambda: signed(other.secret, event.id, event.body)

    _refused(s, make, 401)


@cause("signature-cut", pair=2)
def signature_cut(s):
    def make(feed):
        event = s.order(feed)

        def headers():
            right = signed(feed.secret, event.id, event.body)
            half = base64.b64encode(base64.b64decode(right["webhook-signature"][3:])[:16]).decode()
            return right | {"webhook-signature": f"v1,{half}"}

        return event, headers

    _refused(s, make, 401)


def _clock(s, sign):
    def make(feed):
        event, off = s.order(feed), s.random.randint(400, 4000)
        return event, lambda: signed(feed.secret, event.id, event.body, int(time.time()) + sign * off)

    _refused(s, make, 401)


@cause("clock-behind", pair=3)
def clock_behind(s):
    _clock(s, -1)


@cause("clock-ahead", pair=3)
def clock_ahead(s):
    _clock(s, 1)


@cause("signature-left-out", pair=4)
def signature_left_out(s):
    def make(feed):
        event = s.order(feed)
        return event, lambda: {name: value for name, value in signed(feed.secret, event.id, event.body).items() if name != "webhook-signature"}

    _refused(s, make, 400)


@cause("id-not-allowed", pair=4)
def id_not_allowed(s):
    def make(feed):
        event = s.order(feed, id=f"{new_id(s.random)}.1")
        return event, lambda: signed(feed.secret, event.id, event.body)

    _refused(s, make, 400)


def _comes_again(s, same):
    s.open()
    s.sleep(2, 4)
    for _ in range(s.random.randint(1, 4)):
        event = s.order()
        first = signed(event.feed.secret, event.id, event.body)
        s.shops.send(event, (lambda first=first: first) if same else None)
        s.wait("it is there", lambda event=event: event.answers and event.answers[-1] in (200, 202))
        s.sleep(0.5, 2)
        again = Event(event.feed, event.id, event.data)
        s.shops.send(again, (lambda first=first: first) if same else None)
        s.wait("it came again", lambda again=again: again.answers)
        s.sleep(0.2, 0.6)
    s.sleep(1, 2)
    s.settle()
    s.fact("it was there already", s.said(what="already"))


@cause("feed-repeats", pair=5)
def feed_repeats(s):
    _comes_again(s, False)


@cause("request-replayed", pair=5)
def request_replayed(s):
    _comes_again(s, True)


@cause("feed-reuses-ids", pair=6)
def feed_reuses_ids(s):
    _another_body(s)


@cause("secret-in-other-hands", pair=6)
def secret_in_other_hands(s):
    _another_body(s)


def _effect_twice(s):
    _stands_still(s, "worker.after_claim")
    s.wait("there are two orders", lambda: s.ask("select event_id from orders group by feed, event_id having count(*) = 2"))
    s.sleep(0.5, 2)
    s.settle()
    s.fact("nobody noticed", not s.said(what="lost_claim"))


@cause("mark-for-anybody", "finish.for_anybody", net=False, pair=7)
def mark_for_anybody(s):
    _effect_twice(s)


@cause("loss-ignored", "work.ignores_the_loss", net=False, pair=7)
def loss_ignored(s):
    _effect_twice(s)


def _more_in_the_body(s, name, end):
    """Both get the same number of letters more, because the length of a body is kept."""
    _nobody_understands(s, lambda feed: Event(feed, s.order(feed).id, s.order(feed).body[:-1] + f', "{name}": "{s.random.choice(ITEMS)}"{end}'.encode()))
    s.fact("that is why", s.said(what="given_back", reason="not_json"))


@cause("body-not-json", pair=8)
def body_not_json(s):
    _more_in_the_body(s, "box", ")")


@cause("name-twice-in-body", pair=8)
def name_twice_in_body(s):
    _more_in_the_body(s, "sku", "}")


def _feed_stops(s, tries):
    """From some moment on nothing comes of one feed any more."""
    s.open()
    s.sleep(4, 7)
    feed = s.feed()
    s.only(*[one for one in s.feeds if one is not feed])
    refused = 0
    for _ in range(s.random.randint(5, 8)):
        s.sleep(1, 1.5)
        if tries:
            try:
                socket.create_connection(("127.0.0.1", s.nobody_there), 2).close()
            except ConnectionRefusedError:
                refused += 1
    s.settle()
    s.fact("the others went on", len(s.shops.events) >= 10)
    s.fact("it did not get through", refused >= 5 or not tries)


@cause("feed-silent", pair=9)
def feed_silent(s):
    _feed_stops(s, False)


@cause("feed-cannot-connect", pair=9)
def feed_cannot_connect(s):
    # It tries where nobody listens. The front door cannot see that.
    _feed_stops(s, True)


def _never_taken_back(s):
    _worker_ends(s, "worker.after_claim")
    s.sleep(0.5, 1.5)
    s.worker()
    s.wait("its claim is over for long", lambda: s.one("select count(*) from inbox where state = 'working' and due_at < now() - interval '7 seconds'") == 1, LEASE + 30)
    s.settle(stuck=1)
    s.fact("nobody took it back", s.one("select count(*) from inbox where state = 'working' and attempts = 1 and due_at < now() - interval '7 seconds'") == 1)
    _said_so(s)


@cause("claim-only-what-waits", "claim.only_what_waits", pair=10)
def claim_only_what_waits(s):
    _never_taken_back(s)


@cause("no-careful-loop", "work.no_loop_is_careful", pair=10)
def no_careful_loop(s):
    _never_taken_back(s)
