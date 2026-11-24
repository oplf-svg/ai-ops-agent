"""The programs of the platform while they run: every line that they write with its time, and how they end."""

import os
import signal
import subprocess
import threading
import time


class Clock:
    """Milliseconds since the recording began."""

    def __init__(self):
        self.begin()

    def begin(self):
        self._start = time.monotonic()

    def now(self):
        return max(0, int((time.monotonic() - self._start) * 1000))


class Program:
    """One copy of the API or of the worker."""

    def __init__(self, name, kind, command, environment, clock, heard):
        self.name, self.kind, self.end, self.exit = name, kind, None, None
        self._clock, self._heard = clock, heard
        self._process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        threading.Thread(target=self._wait, daemon=True).start()

    def _read(self):
        for line in self._process.stdout:
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if text:
                self._heard(self, self._clock.now(), text)

    def _wait(self):
        code = self._process.wait()
        # As a shell says it: 137 is killed.
        self.end, self.exit = self._clock.now(), code if code >= 0 else 128 - code

    @property
    def pid(self):
        return self._process.pid

    @property
    def alive(self):
        return self._process.poll() is None

    def send(self, number):
        try:
            os.kill(self.pid, number)
        except ProcessLookupError:
            pass

    def go_on(self):
        self.send(signal.SIGCONT)

    def finish(self):
        """After the recording. A program that stands still has to go on before it can end."""
        if self.alive:
            self.send(signal.SIGKILL)
            self.go_on()
            self._process.wait(20)
        self._reader.join(10)
        self._process.stdout.close()
