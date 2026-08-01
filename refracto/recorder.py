"""Default product-neutral recorder.

Store recorded responses in memory and return defensive copies to callers.
"""
from refracto import ports


class InMemoryRecorder(ports.Recorder):
    def __init__(self):
        self._responses = []

    def record(self, resp) -> None:
        self._responses.append(resp)

    def responses(self) -> list:
        return list(self._responses)
