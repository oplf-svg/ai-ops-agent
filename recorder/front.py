"""The front door: hands each request to a copy of the API and writes down what came of it. And the shops, which send."""

import base64
import hashlib
import heapq
import hmac
import http.client
import itertools
import json
import threading
import time
import urllib.request

from recorder.lines import NO_FEED

# An answer after which a shop sends again. 502 is ours: nobody was there to take the request.
AGAIN = (None, 502, 503)
NOBODY_THERE = 502


class Front:
    """Goes round the copies. One that refuses a connection is left out from then on."""

    def __init__(self, timeout=25.0):
        self._timeout, self._copies, self._turn = timeout, [], itertools.count()
        self.over = threading.Event()

    def add(self, port):
        self._copies.append(port)

    def look_after(self, port, pause=2.0):
        """Asks a copy now and then whether it is ready, as a load balancer does. What it answers is in its own log."""

        def look():
            while not self.over.wait(pause):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=12) as answer:
                        answer.read()
                except OSError:
                    pass

        threading.Thread(target=look, daemon=True).start()

    def send(self, name, headers, body):
        """One request. Returns the status, or None if there was no answer."""
        port = self._copies[next(self._turn) % len(self._copies)]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=self._timeout)
        try:
            connection.connect()
        except OSError:
            # It never came to the API. Whatever else fails from here on may have arrived.
            if len(self._copies) > 1 and port in self._copies:
                self._copies.remove(port)
            return NOBODY_THERE
        try:
            connection.request("POST", f"/hooks/{name}", body, headers)
            answer = connection.getresponse()
            answer.read()
            return answer.status
        except (OSError, http.client.HTTPException):
            return None
        finally:
            connection.close()


def signed(secret, id, body, at=None):
    at = int(time.time()) if at is None else at
    signature = base64.b64encode(hmac.new(secret, f"{id}.{at}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"webhook-id": id, "webhook-timestamp": str(at), "webhook-signature": f"v1,{signature}"}


class Event:
    """What a shop sends. Its name and its number are made up."""

    def __init__(self, feed, id, data):
        self.feed, self.id, self.data = feed, id, data
        self.body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.answers = []

    @property
    def key(self):
        return self.feed.name, self.id


class Shops(threading.Thread):
    """Sends all that the shops send, one request at a time, so it is always clear which one was under way."""

    def __init__(self, front, note, random, make, trouble, every=(0.35, 0.9), again=(0.6, 1.5)):
        super().__init__(daemon=True)
        self._front, self._note, self._random, self._make, self._trouble, self._every, self._again = front, note, random, make, trouble, every, again
        self._queue, self._number, self._lock = [], itertools.count(), threading.Condition()
        self._next, self._busy, self.over = None, False, False
        self.events = []

    def begin(self):
        """From now on new orders come by themselves."""
        with self._lock:
            self._next = time.monotonic()
            self._lock.notify()

    def pause(self):
        with self._lock:
            self._next = None

    def send(self, event, make_headers=None, name=None, again=True, wait=0.0):
        """Sends this one as well. `make_headers` makes what is wrong with it, and `name` is another address."""
        with self._lock:
            heapq.heappush(self._queue, (time.monotonic() + wait, next(self._number), event, make_headers, name, again))
            self._lock.notify()
        return event

    @property
    def idle(self):
        with self._lock:
            return not self._queue and not self._busy

    def run(self):
        try:
            while not self.over:
                self._step()
        except Exception as problem:
            # Without this nobody would hear why nothing is sent any more.
            self._trouble(f"the shops: {problem!r}")

    def _step(self):
        with self._lock:
            now = time.monotonic()
            if self._next is not None and now >= self._next:
                heapq.heappush(self._queue, (now, next(self._number), self._make(), None, None, True))
                self._next = now + self._random.uniform(*self._every)
            due = [one for one in (self._queue[0][0] if self._queue else None, self._next) if one is not None]
            if not self._queue or self._queue[0][0] > now:
                self._lock.wait(min(0.2, max(0.0, min(due) - now)) if due else 0.2)
                return
            _, _, event, make_headers, name, again = heapq.heappop(self._queue)
            self._busy = True
        self._deliver(event, make_headers, name, again)
        with self._lock:
            self._busy = False

    def _deliver(self, event, make_headers, name, again):
        if not event.answers:
            self.events.append(event)
        headers = make_headers() if make_headers else signed(event.feed.secret, event.id, event.body)
        status = self._front.send(name or event.feed.name, headers, event.body)
        self._note("front", feed=NO_FEED if name else event.feed.name, event=event.id, status=status)
        event.answers.append(status)
        if again and status in AGAIN:
            self.send(event, make_headers, name, again, self._random.uniform(*self._again))
