import pytest

from refracto import asyncwait as aw


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def test_succeeds_before_timeout():
    clock = FakeClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return (calls["n"] >= 3, calls["n"])

    res = aw.wait_until(fn, timeout=10, interval=1, on_timeout=aw.FAIL,
                        now=clock.now, sleep=clock.sleep)
    assert res.ok and res.value == 3 and not res.timed_out


def test_fail_policy_raises_on_timeout():
    clock = FakeClock()
    with pytest.raises(TimeoutError):
        aw.wait_until(lambda: (False, None), timeout=3, interval=1,
                      on_timeout=aw.FAIL, now=clock.now, sleep=clock.sleep)


def test_skip_policy_returns_skipped():
    clock = FakeClock()
    res = aw.wait_until(lambda: (False, None), timeout=3, interval=1,
                        on_timeout=aw.SKIP, now=clock.now, sleep=clock.sleep)
    assert res.skipped and not res.ok and res.timed_out


def test_retry_policy_is_typed_not_tuple():
    r = aw.retry(3)
    assert isinstance(r, aw.Retry) and r.attempts == 3


def test_retry_policy_reattempts_then_succeeds():
    clock = FakeClock()
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        return (attempts["n"] >= 5, attempts["n"])

    res = aw.wait_until(fn, timeout=2, interval=1, on_timeout=aw.retry(3),
                        now=clock.now, sleep=clock.sleep)
    assert res.ok
    assert res.value == 5
    assert res.timed_out is False
    assert res.skipped is False


def test_retry_exhaustion_returns_wait_result():
    clock = FakeClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return (False, None)

    res = aw.wait_until(fn, timeout=1, interval=1, on_timeout=aw.retry(2),
                        now=clock.now, sleep=clock.sleep)
    assert res.ok is False
    assert res.timed_out is True
    assert res.skipped is False
    assert calls["n"] > 1
