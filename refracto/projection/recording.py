"""Preserve core-owned response evidence across an untrusted Recorder seam."""
import copy
import math
import struct
from dataclasses import fields

from refracto.declaration.values import equal
from refracto.ports import RecordedResponse, RequestSpec


def _evidence_equal(actual, expected):
    """Snapshot fidelity is not a business comparison or value-validity rule.

    A malformed observed NaN must remain recordable so declaration consumers
    can reject it at their own boundary. Compare its exact IEEE-754 payload;
    do not change the assertion/reference comparator's NaN semantics.
    """
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return ({(type(key), key) for key in actual} == {(type(key), key) for key in expected}
                and all(_evidence_equal(actual[key], expected[key]) for key in actual))
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_evidence_equal(a, b) for a, b in zip(actual, expected))
    if type(actual) is float and (math.isnan(actual) or math.isnan(expected)):
        return struct.pack("!d", actual) == struct.pack("!d", expected)
    return equal(actual, expected)


def _same_recording(actual, expected):
    if type(actual) is not RecordedResponse or type(expected) is not RecordedResponse:
        return False
    if type(actual.request) is not RequestSpec or type(expected.request) is not RequestSpec:
        return False
    if not all(_evidence_equal(getattr(actual.request, item.name), getattr(expected.request, item.name))
               for item in fields(RequestSpec)):
        return False
    return all(item.name == "request" or _evidence_equal(getattr(actual, item.name), getattr(expected, item.name))
               for item in fields(RecordedResponse))


class ProtectedRecorder:
    """Check every append/read; only verified core snapshots leave this wrapper."""
    def __init__(self, recorder):
        self._recorder = recorder
        self._expected = []
        self._failed = False

    def _check(self, expected):
        try:
            observed = self._recorder.responses()
        except Exception:
            raise ValueError("Recorder could not return recorded evidence") from None
        if type(observed) is not list or len(observed) != len(expected):
            raise ValueError("Recorder response count mismatch")
        if not all(_same_recording(a, b) for a, b in zip(observed, expected)):
            raise ValueError("Recorder changed response evidence or order")

    def record(self, response):
        if self._failed:
            raise ValueError("Recorder previously failed evidence validation")
        protected = copy.deepcopy(response)
        expected = [*self._expected, protected]
        try:
            try:
                self._recorder.record(copy.deepcopy(protected))
            except Exception:
                raise ValueError("Recorder could not record response evidence") from None
            self._check(expected)
        except Exception:
            self._failed = True
            raise
        self._expected = expected

    def responses(self):
        # A failed append has already produced a step ERROR. Retain prior,
        # verified evidence without reading a now-untrusted adapter again.
        if not self._failed:
            self._check(self._expected)
        return copy.deepcopy(self._expected)
