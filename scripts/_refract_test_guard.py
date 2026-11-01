"""Private, explicitly loaded progress plugin for scripts/run_tests.py.

The one-shot bootstrap is removed from the environment at import time. A nested
pytest therefore cannot acquire this invocation's progress file by inheritance.
"""

import atexit
import faulthandler
import json
import os
from pathlib import Path
import signal

import pytest


_BOOTSTRAP = os.environ.pop("_REFRACT_TEST_GUARD", None)
_STATE = None


def _label(value):
    return "".join(c for c in str(value).split("[", 1)[0] if c.isprintable())[:200]


class _Progress:
    def __init__(self, bootstrap):
        self.pid = os.getpid()
        self.execution_id = bootstrap["execution_id"]
        self.directory = Path(bootstrap["directory"])
        self.root = Path(bootstrap["root"])
        self.sequence = 0
        self.test = None
        self.ordinals = {}
        # Keep this handle and signal registration alive through Python shutdown.
        self.stack = (self.directory / "stacks.log").open("a", encoding="utf-8")
        self.ready = False
        try:
            faulthandler.register(signal.SIGUSR1, file=self.stack, all_threads=True)
            self.ready = True
        except (OSError, RuntimeError):
            pass
        self.write("startup")
        atexit.register(self.finish)

    def write(self, phase, item=None, *, final=False):
        # Forked children must not write the parent's record or run its atexit.
        if os.getpid() != self.pid:
            return
        if item is not None:
            path = Path(str(item.path)).resolve()
            try:
                filename = path.relative_to(self.root).as_posix()
            except ValueError:
                filename = path.name
            self.test = {
                "file": _label(filename),
                "class": _label(item.cls.__name__) if getattr(item, "cls", None) else None,
                "function": _label(getattr(item, "originalname", None) or item.name),
                "ordinal": self.ordinals.get(id(item)),
            }
        self.sequence += 1
        record = {
            "schema": 1, "execution_id": self.execution_id, "pid": self.pid,
            "sequence": self.sequence, "phase": phase, "test": self.test,
            "diagnostic_ready": self.ready, "final": final,
        }
        temporary = self.directory / "progress.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=True) + "\n", encoding="utf-8")
        temporary.replace(self.directory / "progress.json")

    def finish(self):
        self.write("process_exit", final=True)


if _BOOTSTRAP:
    _STATE = _Progress(json.loads(_BOOTSTRAP))


def _write(phase, item=None):
    if _STATE is not None:
        _STATE.write(phase, item)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    _write("collection")
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection(session):
    _write("collection")
    yield


def pytest_collection_modifyitems(items):
    if _STATE is not None:
        _STATE.ordinals = {id(item): ordinal for ordinal, item in enumerate(items, 1)}


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    _write("setup", item)
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    _write("call", item)
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    _write("teardown", item)
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    _write("finalization")
    yield
    _write("process_exit")
