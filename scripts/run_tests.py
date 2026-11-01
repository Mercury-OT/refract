#!/usr/bin/env python3
"""Bounded POSIX pytest entry; plain pytest remains available independently.

Usage: python scripts/run_tests.py --output-dir NEW_DIR -- [pytest arguments]
Only the new pytest process group is cleaned. Descendants which create another
session escape that boundary; this launcher is not a process sandbox. Hard OS
termination and uninterruptible kernel work also require an outer job ceiling.
"""

import argparse
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid


PHASES = {"startup", "collection", "setup", "call", "teardown", "finalization", "process_exit"}
POLL_SECONDS = 0.05
GUARD_FAILURE = 70
TIMEOUT = 124
DIAGNOSTIC_GRACE = 0.1


def positive_seconds(value):
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected positive finite seconds") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("expected positive finite seconds")
    return number


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--diagnostic-after", type=positive_seconds, default=120.0)
    parser.add_argument("--phase-timeout", type=positive_seconds, default=300.0)
    parser.add_argument("--suite-timeout", type=positive_seconds, default=2700.0)
    parser.add_argument("--terminate-grace", type=positive_seconds, default=2.0)
    parser.add_argument("--kill-grace", type=positive_seconds, default=2.0)
    parser.add_argument("--progress-interval", type=positive_seconds, default=30.0)
    separator = argv.index("--") if "--" in argv else len(argv)
    options = parser.parse_args(argv[:separator])
    pytest_args = argv[separator + 1:]
    if options.diagnostic_after >= options.phase_timeout:
        parser.error("--diagnostic-after must be shorter than --phase-timeout")
    if sys.platform not in {"linux", "darwin"}:
        parser.error("the guarded entry supports Linux and macOS only")
    return options, pytest_args


def atomic_json(path, value):
    # Own a newly created regular descriptor; a stale named temporary file (or
    # FIFO) must never hold the supervisor's final writer outside its deadlines.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as destination:
            destination.write(json.dumps(value, ensure_ascii=True) + "\n")
        os.replace(temporary, path)
    finally:
        os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def startup_record(execution_id):
    # The supervisor creates this before spawning, avoiding races with the child.
    # It is retained on startup failure but is never accepted as a child handshake.
    return {
        "schema": 1, "execution_id": execution_id, "pid": None, "sequence": 0,
        "phase": "startup", "test": None, "diagnostic_ready": False, "final": False,
    }


def read_progress(path, execution_id, pid, previous):
    try:
        # Validate the opened descriptor, not a prior pathname stat: replacement
        # with a FIFO must not block the supervisor before it checks its deadlines.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("invalid_progress")
            raw = os.read(descriptor, 65537).decode("utf-8")
        finally:
            os.close(descriptor)
    except (OSError, UnicodeError) as error:
        raise ValueError("invalid_progress") from error
    if len(raw) > 65536:
        raise ValueError("invalid_progress")
    record = json.loads(raw)
    required = {"schema", "execution_id", "pid", "sequence", "phase", "test", "diagnostic_ready", "final"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("invalid_progress")
    if type(record["schema"]) is not int or record["schema"] != 1:
        raise ValueError("invalid_progress")
    if record == startup_record(execution_id):
        if previous is not None:
            raise ValueError("stale_progress")
        return None
    if (record["execution_id"] != execution_id
            or type(record["pid"]) is not int or record["pid"] != pid
            or type(record["sequence"]) is not int or record["sequence"] < 1
            or record["phase"] not in PHASES
            or type(record["diagnostic_ready"]) is not bool or type(record["final"]) is not bool
            or (record["final"] and record["phase"] != "process_exit")):
        raise ValueError("invalid_progress")
    test = record["test"]
    if test is not None:
        if not isinstance(test, dict) or set(test) != {"file", "class", "function", "ordinal"}:
            raise ValueError("invalid_progress")
        for key in ("file", "class", "function"):
            value = test[key]
            if key == "class" and value is None:
                continue
            if (not isinstance(value, str) or len(value) > 200
                    or not value.isprintable() or "[" in value):
                raise ValueError("invalid_progress")
        if (Path(test["file"]).is_absolute() or ".." in Path(test["file"]).parts
                or type(test["ordinal"]) is not int or test["ordinal"] < 1):
            raise ValueError("invalid_progress")
    if previous is not None:
        if record["sequence"] < previous["sequence"]:
            raise ValueError("stale_progress")
        if record["sequence"] == previous["sequence"] and record != previous:
            raise ValueError("invalid_progress")
        if previous["final"] and record != previous:
            raise ValueError("invalid_progress")
    return record


def record_cleanup_error(errors, operation, error):
    entry = {"operation": operation, "exception": type(error).__name__, "errno": getattr(error, "errno", None)}
    if entry not in errors:
        errors.append(entry)


def group_members(pgid, errors=None):
    """Return live owned members; zombies cannot run or hold output descriptors.

    ps is bounded independently and used only for this dedicated process group.
    An inspection failure is unknown, never evidence that cleanup succeeded.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return []
    except PermissionError as error:
        # Darwin can return EPERM for a zombie-only group. The bounded process
        # listing below distinguishes that state from live inaccessible members.
        if errors is not None:
            record_cleanup_error(errors, "group_probe", error)
    except OSError as error:
        if errors is not None:
            record_cleanup_error(errors, "group_probe", error)
        return None
    try:
        with tempfile.TemporaryFile(mode="w+b") as output:
            probe = subprocess.Popen(
                ["ps", "-axo", "pid=,pgid=,stat="], stdout=output,
                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            )
            try:
                probe.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                probe.kill()
                try:
                    probe.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
                return None
            if probe.returncode:
                return None
            output.seek(0)
            listing = output.read().decode("ascii", errors="replace")
        members = []
        for line in listing.splitlines():
            fields = line.split()
            if len(fields) == 3 and int(fields[1]) == pgid and not fields[2].startswith("Z"):
                members.append(int(fields[0]))
        return members
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        if errors is not None:
            record_cleanup_error(errors, "group_inspection", error)
        return None


def cleanup(child, terminate_grace, kill_grace, outcome=None):
    if outcome is None:
        outcome = {"term_sent": False, "kill_sent": False, "remaining_pids": [], "errors": []}
    outcome["complete"] = False

    def poll():
        try:
            child.poll()
        except (OSError, RuntimeError) as error:
            record_cleanup_error(outcome["errors"], "child_poll", error)

    members = group_members(child.pid, outcome["errors"])
    for sig, grace, key in ((signal.SIGTERM, terminate_grace, "term_sent"),
                            (signal.SIGKILL, kill_grace, "kill_sent")):
        poll()
        if members == [] and child.returncode is not None:
            outcome["complete"] = True
            return outcome
        try:
            os.killpg(child.pid, sig)
            outcome[key] = True
        except ProcessLookupError:
            pass
        except OSError as error:
            # A signal can race with exit or fail for a live member. Preserve the
            # evidence and still inspect/escalate; only observed emptiness is clean.
            record_cleanup_error(outcome["errors"], f"send_{sig.name.lower()}", error)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            poll()
            members = group_members(child.pid, outcome["errors"])
            if members == [] and child.returncode is not None:
                outcome["complete"] = True
                return outcome
            time.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))
    poll()
    outcome["remaining_pids"] = members
    return outcome


def display(record, elapsed):
    active = record["test"] if record else None
    phase = record["phase"] if record else "startup"
    identity = ""
    if active:
        identity = f" {active['file']}::{active['function']} (test {active['ordinal']})"
    print(f"test guard: {phase}{identity}; elapsed {elapsed:.1f}s", flush=True)


def request_diagnostic(child, record, diagnostics):
    diagnostics["requests"] += 1
    if record and record["diagnostic_ready"] and child.poll() is None:
        try:
            os.kill(child.pid, signal.SIGUSR1)
            diagnostics["signal_delivered"] = True
            return True
        except ProcessLookupError:
            pass
    return False


def run(options, pytest_args):
    directory = options.output_dir.resolve()
    try:
        # An empty, pre-created directory is allowed; no existing file is reused.
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            print("test guard: output directory must be empty", file=sys.stderr)
            return 2
        for name in ("pytest.log", "stacks.log"):
            (directory / name).touch(exist_ok=False)
    except OSError:
        print("test guard: cannot create output directory", file=sys.stderr)
        return 2
    execution_id = uuid.uuid4().hex
    started = time.monotonic()
    phase_started = started
    next_status = started
    previous = None
    reason = None
    child = None
    interrupted = []
    diagnostics = {"ready": False, "requests": 0, "signal_delivered": False, "stack_bytes": 0}
    requested_sequence = None
    cleanup_outcome = {"complete": True, "term_sent": False, "kill_sent": False, "remaining_pids": [], "errors": []}
    old_handlers = {}

    def interrupt(signum, frame):
        if not interrupted:
            interrupted.append(signum)

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, interrupt)
        atomic_json(directory / "progress.json", startup_record(execution_id))
        environment = os.environ.copy()
        scripts = str(Path(__file__).resolve().parent)
        environment["PYTHONPATH"] = scripts + os.pathsep + environment.get("PYTHONPATH", "")
        environment["_REFRACT_TEST_GUARD"] = json.dumps({
            "execution_id": execution_id, "directory": str(directory),
            "root": str(Path(__file__).resolve().parent.parent),
        })
        with (directory / "pytest.log").open("ab", buffering=0) as log:
            child = subprocess.Popen(
                [sys.executable, "-m", "pytest", "-p", "_refract_test_guard", *pytest_args],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                env=environment, start_new_session=True,
            )
        while True:
            now = time.monotonic()
            record = read_progress(directory / "progress.json", execution_id, child.pid, previous)
            if record is not None:
                diagnostics["ready"] = diagnostics["ready"] or record["diagnostic_ready"]
                if previous is None or record["sequence"] != previous["sequence"]:
                    phase_started = now
                previous = record
            if interrupted:
                reason = "interrupted"
                break
            # Deadlines are checked even when poll would report a zero exit.
            if now - started >= options.suite_timeout:
                reason = "suite_timeout"
                break
            if now - phase_started >= options.phase_timeout:
                reason = "phase_timeout"
                break
            if child.poll() is not None:
                # Read once more after exit to see the last atomic atexit record.
                previous = read_progress(directory / "progress.json", execution_id, child.pid, previous)
                if previous is not None:
                    diagnostics["ready"] = diagnostics["ready"] or previous["diagnostic_ready"]
                if previous is None or not diagnostics["ready"] or not previous["final"]:
                    reason = "incomplete_progress"
                else:
                    members = group_members(child.pid, cleanup_outcome["errors"])
                    if members is None:
                        reason = "group_inspection_failed"
                    elif members:
                        reason = "surviving_group_members"
                break
            sequence = previous["sequence"] if previous else 0
            if now - phase_started >= options.diagnostic_after and requested_sequence != sequence:
                requested_sequence = sequence
                request_diagnostic(child, previous, diagnostics)
            if now >= next_status:
                display(previous, now - started)
                next_status = now + options.progress_interval
            time.sleep(POLL_SECONDS)
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        reason = "stale_progress" if str(error) == "stale_progress" else "invalid_progress"
    except (OSError, RuntimeError):
        reason = "supervisor_failure"
    except KeyboardInterrupt:
        interrupted.append(signal.SIGINT)
        reason = "interrupted"
    finally:
        if child is not None:
            if reason in {"suite_timeout", "phase_timeout", "interrupted"}:
                try:
                    if request_diagnostic(child, previous, diagnostics):
                        # A small fixed capture grace also applies when a short suite
                        # ceiling or interrupt arrives before the diagnostic delay.
                        time.sleep(DIAGNOSTIC_GRACE)
                except (OSError, RuntimeError) as error:
                    record_cleanup_error(cleanup_outcome["errors"], "diagnostic_signal", error)
            try:
                cleanup(child, options.terminate_grace, options.kill_grace, cleanup_outcome)
            except (OSError, RuntimeError) as error:
                cleanup_outcome["complete"] = False
                cleanup_outcome["remaining_pids"] = None
                record_cleanup_error(cleanup_outcome["errors"], "cleanup", error)
            if not cleanup_outcome["complete"] and reason is None:
                reason = "incomplete_cleanup"
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    if interrupted:
        reason = "interrupted"
    try:
        diagnostics["stack_bytes"] = (directory / "stacks.log").stat().st_size
    except OSError:
        diagnostics["stack_bytes"] = None
        diagnostics["capture_error"] = "stack_file_unavailable"
        reason = reason or "supervisor_failure"
    if reason == "interrupted":
        exit_code = 128 + interrupted[0]
    elif reason in {"suite_timeout", "phase_timeout"}:
        exit_code = TIMEOUT
    elif reason:
        exit_code = GUARD_FAILURE
    else:
        exit_code = child.returncode
        if exit_code < 0:
            exit_code = 128 - exit_code
    result = {
        "schema": 1, "execution_id": execution_id, "pid": child.pid if child else None,
        "budgets": {name: getattr(options, name) for name in (
            "diagnostic_after", "phase_timeout", "suite_timeout", "terminate_grace", "kill_grace")},
        "diagnostic_grace_seconds": DIAGNOSTIC_GRACE,
        "last_progress": previous, "elapsed_seconds": time.monotonic() - started,
        "phase_elapsed_seconds": time.monotonic() - phase_started,
        "child_exit_code": child.returncode if child else None,
        "exit_code": exit_code, "reason": reason or "pytest_exit",
        "diagnostics": diagnostics, "cleanup": cleanup_outcome,
    }
    try:
        atomic_json(directory / "result.json", result)
    except OSError:
        print("test guard: cannot retain final result", file=sys.stderr)
        return GUARD_FAILURE
    display(previous, result["elapsed_seconds"])
    print(f"test guard: {result['reason']}; exit {exit_code}; cleanup complete={cleanup_outcome['complete']}", flush=True)
    return exit_code


def main(argv=None):
    options, pytest_args = arguments(sys.argv[1:] if argv is None else argv)
    return run(options, pytest_args)


if __name__ == "__main__":
    sys.exit(main())
