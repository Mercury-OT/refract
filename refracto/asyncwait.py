"""Universal async-wait primitive.

Polling throughout the framework goes through this helper so timeout handling
remains explicit at the call site.
"""
import time
from dataclasses import dataclass

FAIL = "FAIL"
SKIP = "SKIP"


@dataclass(frozen=True)
class Retry:
    attempts: int


def retry(n: int):
    return Retry(attempts=n)


@dataclass
class WaitResult:
    ok: bool
    value: object = None
    timed_out: bool = False
    skipped: bool = False


def _poll_once_window(fn, timeout, interval, now, sleep):
    start = now()
    while True:
        done, value = fn()
        if done:
            return True, value
        if now() - start >= timeout:
            return False, value
        sleep(interval)


def wait_until(fn, timeout, interval=0.5, on_timeout=FAIL, now=None, sleep=None):
    now = now or time.monotonic
    sleep = sleep or time.sleep

    if isinstance(on_timeout, Retry):
        attempts = on_timeout.attempts
        last = None
        for _ in range(attempts):
            ok, last = _poll_once_window(fn, timeout, interval, now, sleep)
            if ok:
                return WaitResult(ok=True, value=last)
        return WaitResult(ok=False, value=last, timed_out=True)

    ok, value = _poll_once_window(fn, timeout, interval, now, sleep)
    if ok:
        return WaitResult(ok=True, value=value)
    if on_timeout == SKIP:
        return WaitResult(ok=False, value=value, timed_out=True, skipped=True)
    raise TimeoutError(f"wait_until timed out after {timeout}s (policy=FAIL)")
