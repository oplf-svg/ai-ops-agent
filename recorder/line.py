"""A line to the database that is cut at a chosen moment."""

import socket
import threading


class Line:
    """Cuts when something was asked for the so-many-eth time: after the database did it and before its answer arrives, or before it
    is asked at all."""

    def __init__(self, target, what, times, before=False):
        self._target, self._what, self._times, self._before = target, what, frozenset(times), before
        self.seen = self.cut = 0
        self._lock = threading.Lock()
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                near, _ = self._listener.accept()
            except OSError:
                return
            try:
                far = socket.create_connection(("127.0.0.1", self._target))
            except OSError:
                near.close()
                continue
            swallow = threading.Event()
            threading.Thread(target=self._ask, args=(near, far, swallow), daemon=True).start()
            threading.Thread(target=self._answer, args=(near, far, swallow), daemon=True).start()

    def _is_time(self, data):
        if not self._what.search(data):
            return False
        with self._lock:
            self.seen += 1
            return self.seen in self._times

    def _ask(self, near, far, swallow):
        try:
            while data := near.recv(1 << 16):
                if self._is_time(data):
                    if self._before:
                        with self._lock:
                            self.cut += 1
                        break
                    swallow.set()
                far.sendall(data)
        except OSError:
            pass
        self._close(near, far)

    def _answer(self, near, far, swallow):
        try:
            while data := far.recv(1 << 16):
                if swallow.is_set():
                    with self._lock:
                        self.cut += 1
                    break
                near.sendall(data)
        except OSError:
            pass
        self._close(near, far)

    @staticmethod
    def _close(*ends):
        for end in ends:
            try:
                end.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            end.close()

    def end(self):
        self._close(self._listener)
