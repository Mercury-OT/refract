"""Real pytest controls with an independent outer deadline and owned-PID cleanup."""

import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run_tests.py"
pytestmark = pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="POSIX guard")


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="], capture_output=True,
        text=True, timeout=1, check=False,
    ).stdout.strip()
    return bool(status) and not status.startswith("Z")


def _kill_owned(pid, *, group=False):
    assert type(pid) is int and pid > 1, "cleanup requires a specific owned process"
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail("synthetic control did not reach its expected state")


class GuardRun:
    def __init__(self, directory, source="def test_ok(): pass\n", conftest="", sitecustomize=""):
        self.directory = directory
        self.output = directory / "guard"
        self.pids = directory / "owned-pids"
        self.pytest_pid = directory / "pytest-pid"
        self.process = None
        self.log = None
        (directory / "test_control.py").write_text(source, encoding="utf-8")
        (directory / "conftest.py").write_text(conftest, encoding="utf-8")
        # Independent ownership evidence, written before the guard plugin loads.
        # Never derive cleanup targets from deliberately corrupted progress files.
        startup = (
            "import os\nfrom pathlib import Path\n"
            "if '_REFRACT_TEST_GUARD' in os.environ:\n"
            f"    with Path({str(self.pytest_pid)!r}).open('x') as marker:\n"
            "        marker.write(str(os.getpid()))\n"
        )
        (directory / "sitecustomize.py").write_text(startup + sitecustomize, encoding="utf-8")

    def start(self, *pytest_args, extra=(), env=None):
        self.log = (self.directory / "supervisor.log").open("wb")
        self.started = time.monotonic()
        self.process = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "--output-dir", str(self.output),
             "--diagnostic-after", "0.2", "--phase-timeout", "1.2",
             "--suite-timeout", "8", "--terminate-grace", "0.2", "--kill-grace", "0.4",
             "--progress-interval", "0.3", *extra, "--", "-q", "-o", "addopts=",
             "--confcutdir", str(self.directory), *pytest_args],
            cwd=self.directory, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": "",
                 "PYTHONPATH": str(self.directory), **(env or {})},
            start_new_session=True,
        )
        return self

    def finish(self, timeout=12):
        # This outer bound remains independent of every budget in the launcher.
        self.process.wait(timeout=timeout)
        self.elapsed = time.monotonic() - self.started
        self.log.close()
        self.result = json.loads((self.output / "result.json").read_text())
        self.text = (self.directory / "supervisor.log").read_text()
        return self

    def close(self):
        # A defective launcher must not leave any of the synthetic controls behind.
        if self.pytest_pid.exists():
            _kill_owned(int(self.pytest_pid.read_text()), group=True)
        if self.pids.exists():
            for pid in self.pids.read_text().split():
                _kill_owned(int(pid))
        if self.process is not None:
            if self.process.poll() is None:
                _kill_owned(self.process.pid, group=True)
            self.process.wait(timeout=2)
        if self.log is not None:
            self.log.close()


@pytest.fixture
def control(tmp_path):
    runs = []

    def create(source="def test_ok(): pass\n", conftest="", sitecustomize=""):
        directory = tmp_path / str(len(runs))
        directory.mkdir()
        run = GuardRun(directory, source, conftest, sitecustomize)
        runs.append(run)
        return run

    yield create
    for run in reversed(runs):
        run.close()


@pytest.mark.parametrize("source,args,expected", [
    ("def test_ok(): pass\n", (), 0),
    ("def test_failure(): assert False\n", (), 1),
    ("raise RuntimeError('collection control')\n", (), 2),
    ("value = 1\n", (), 5),
    ("def test_ok(): pass\n", ("--invalid-pytest-option",), 4),
])
def test_ordinary_pytest_exit_codes(control, source, args, expected):
    run = control(source).start(*args).finish()
    assert run.process.returncode == expected, run.text
    assert run.result["child_exit_code"] == expected
    assert run.result["reason"] == "pytest_exit"
    assert run.result["last_progress"]["final"] is True
    assert run.result["diagnostics"]["ready"] is True
    assert run.result["cleanup"]["complete"] is True


@pytest.mark.parametrize("phase,source,conftest", [
    ("collection", "import time\ntime.sleep(30)\n", ""),
    ("setup", "def test_stall(fixture): pass\n",
     "import pytest, time\n"
     "@pytest.fixture\ndef fixture(): time.sleep(30)\n"),
    ("call", "import time\ndef test_stall(): time.sleep(30)\n", ""),
    ("teardown", "def test_stall(fixture): pass\n",
     "import pytest, time\n"
     "@pytest.fixture\ndef fixture():\n    yield\n    time.sleep(30)\n"),
    ("finalization", "def test_stall(): pass\n",
     "import time\ndef pytest_sessionfinish(session, exitstatus): time.sleep(30)\n"),
    ("process_exit", "def test_stall(): pass\n",
     "import atexit, time\natexit.register(lambda: time.sleep(30))\n"),
    ("call", "import subprocess, sys\ndef test_stall():\n"
     "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']).wait()\n", ""),
])
def test_each_stalled_phase_is_bounded_and_has_stacks(control, phase, source, conftest):
    run = control(source, conftest).start().finish()
    assert run.process.returncode == 124, run.text
    assert run.result["reason"] == "phase_timeout"
    assert run.result["last_progress"]["phase"] == phase
    assert run.result["diagnostics"]["signal_delivered"] is True
    assert run.result["diagnostics"]["stack_bytes"] > 0
    assert run.result["cleanup"]["complete"] is True
    assert run.elapsed < 5
    if phase != "collection":
        assert run.result["last_progress"]["test"]["function"] == "test_stall"


def test_startup_without_ready_handler_is_bounded(control):
    run = control(sitecustomize=(
        "import os, time\n"
        "if '_REFRACT_TEST_GUARD' in os.environ: time.sleep(30)\n"
    )).start(extra=("--suite-timeout", "0.7")).finish()
    assert run.process.returncode == 124
    assert run.result["reason"] == "suite_timeout"
    assert run.result["last_progress"] is None
    assert json.loads((run.output / "progress.json").read_text())["phase"] == "startup"
    assert run.result["diagnostics"]["signal_delivered"] is False
    assert run.result["cleanup"]["complete"] is True


def test_phase_progress_does_not_reset_suite_ceiling(control):
    source = "import time\n" + "\n".join(
        f"def test_{index}(): time.sleep(0.3)" for index in range(12)
    )
    run = control(source).start(extra=("--suite-timeout", "1.0")).finish()
    assert run.process.returncode == 124
    assert run.result["reason"] == "suite_timeout"
    assert run.result["last_progress"]["test"]["ordinal"] >= 2


def test_suite_ceiling_before_soft_delay_still_requests_stacks(control):
    run = control("import time\ndef test_wait(): time.sleep(30)\n").start(
        extra=("--diagnostic-after", "2", "--phase-timeout", "3", "--suite-timeout", "0.7"),
    ).finish()
    assert run.process.returncode == 124
    assert run.result["reason"] == "suite_timeout"
    assert run.result["diagnostics"]["signal_delivered"] is True
    assert run.result["diagnostics"]["stack_bytes"] > 0


def test_missing_readiness_cannot_report_success(control):
    run = control(sitecustomize="import os\nos.environ.pop('_REFRACT_TEST_GUARD', None)\n").start().finish()
    assert run.result["child_exit_code"] == 0
    assert run.process.returncode == 70
    assert run.result["reason"] == "incomplete_progress"


@pytest.mark.parametrize("kind", ["malformed", "missing", "stale", "wrong_owner", "boolean_schema", "missing_final"])
def test_invalid_guard_state_cannot_report_success(control, kind):
    statements = {
        "malformed": "path.write_text('{broken')\ntime.sleep(30)",
        "missing": "path.unlink()\ntime.sleep(30)",
        "stale": "temporary = path.with_name('control-progress.tmp')\n"
                 "record['sequence'] += 100\ntemporary.write_text(json.dumps(record))\ntemporary.replace(path)\n"
                 "observed = path.parent.parent / 'observed-sequence'\n"
                 "deadline = time.monotonic() + 1\n"
                 "while time.monotonic() < deadline:\n"
                 "    if observed.exists() and observed.read_text() == str(record['sequence']): break\n"
                 "    time.sleep(0.01)\n"
                 "assert observed.exists() and observed.read_text() == str(record['sequence'])\n"
                 "record['sequence'] -= 1\n"
                 "observed.with_name('rollback-ready').write_text(str(record['sequence']))\n"
                 "temporary.write_text(json.dumps(record))\ntemporary.replace(path)\ntime.sleep(30)",
        "wrong_owner": "record['pid'] += 1\npath.write_text(json.dumps(record))\ntime.sleep(30)",
        "boolean_schema": "record['schema'] = True\npath.write_text(json.dumps(record))\ntime.sleep(30)",
        "missing_final": "os._exit(0)",
    }
    source = (
        "import json, os, time, _refract_test_guard\n"
        "def test_state():\n"
        "    path = _refract_test_guard._STATE.directory / 'progress.json'\n"
        "    record = json.loads(path.read_text())\n"
        + "\n".join("    " + line for line in statements[kind].splitlines()) + "\n"
    )
    observer = ""
    if kind == "stale":
        observer = (
            "import json, os\nfrom pathlib import Path\n"
            "if '_REFRACT_TEST_GUARD' not in os.environ:\n"
            "    original_loads = json.loads\n"
            "    observation = Path(__file__).with_name('observed-sequence')\n"
            "    def observed_loads(*args, **kwargs):\n"
            "        value = original_loads(*args, **kwargs)\n"
            "        if isinstance(value, dict) and type(value.get('sequence')) is int:\n"
            "            temporary = observation.with_suffix('.tmp')\n"
            "            temporary.write_text(str(value['sequence']))\n"
            "            temporary.replace(observation)\n"
            "        return value\n"
            "    json.loads = observed_loads\n"
        )
    run = control(source, sitecustomize=observer).start().finish()
    assert run.process.returncode == 70, run.text
    assert run.result["reason"] == {
        "malformed": "invalid_progress", "missing": "invalid_progress", "stale": "stale_progress",
        "wrong_owner": "invalid_progress", "boolean_schema": "invalid_progress",
        "missing_final": "incomplete_progress",
    }[kind]
    assert run.result["cleanup"]["complete"] is True
    if kind == "stale":
        assert (run.directory / "rollback-ready").exists()


@pytest.mark.parametrize("replacement", ["os.mkfifo(path)", "path.mkdir()"])
def test_nonregular_progress_cannot_block_supervisor_deadlines(control, replacement):
    source = (
        "import os, time, _refract_test_guard\n"
        "def test_replace_progress():\n"
        "    path = _refract_test_guard._STATE.directory / 'progress.json'\n"
        "    path.unlink()\n"
        f"    {replacement}\n"
        "    time.sleep(30)\n"
    )
    run = control(source).start(
        extra=("--phase-timeout", "0.6", "--suite-timeout", "2"),
    ).finish(timeout=5)
    assert run.process.returncode == 70, run.text
    assert run.result["reason"] == "invalid_progress"
    assert run.result["cleanup"]["complete"] is True
    assert run.elapsed < 4


def test_existing_result_temporary_fifo_cannot_block_final_writer(control):
    source = (
        "import os, _refract_test_guard\n"
        "def test_temporary_fifo():\n"
        "    os.mkfifo(_refract_test_guard._STATE.directory / 'result.tmp')\n"
    )
    run = control(source).start(extra=("--suite-timeout", "2")).finish(timeout=5)
    assert run.process.returncode == 0, run.text
    assert run.result["reason"] == "pytest_exit"
    assert run.result["last_progress"]["final"] is True
    assert run.result["cleanup"]["complete"] is True
    assert stat.S_ISFIFO((run.output / "result.tmp").stat().st_mode)
    assert not list(run.output.glob(".result.json.*.tmp"))
    assert not list(run.output.glob(".progress.json.*.tmp"))
    assert run.elapsed < 4


def test_nested_pytest_cannot_overwrite_parent_progress(control):
    source = (
        "import os, subprocess, sys\nfrom pathlib import Path\n"
        "def test_nested():\n"
        "    assert '_REFRACT_TEST_GUARD' not in os.environ\n"
        "    Path('nested').mkdir()\n"
        "    Path('nested/test_nested.py').write_text('def test_inner(): pass\\n')\n"
        "    result = subprocess.run([sys.executable, '-m', 'pytest', '-p', '_refract_test_guard',\n"
        "        '-q', 'nested'], stdout=subprocess.DEVNULL,\n"
        "        stderr=subprocess.DEVNULL, timeout=3)\n"
        "    assert result.returncode == 0\n"
    )
    run = control(source).start().finish()
    assert run.process.returncode == 0, run.text
    assert run.result["last_progress"]["test"]["function"] == "test_nested"
    assert run.result["pid"] == int(run.pytest_pid.read_text())


def test_missing_stack_file_keeps_an_unsuccessful_final_result(control):
    source = (
        "import _refract_test_guard\n"
        "def test_remove_stack():\n"
        "    (_refract_test_guard._STATE.directory / 'stacks.log').unlink()\n"
    )
    run = control(source).start().finish()
    assert run.process.returncode == 70
    assert run.result["reason"] == "supervisor_failure"
    assert run.result["diagnostics"]["capture_error"] == "stack_file_unavailable"
    assert run.result["cleanup"]["complete"] is True


def _spawn_source(run, *, escaped=False, resistant=False, stall=False):
    ready = run.directory / "child-ready"
    code = "import signal, time; from pathlib import Path; "
    if resistant:
        code += "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    code += f"Path({str(ready)!r}).write_text('ready'); time.sleep(30)"
    return (
        "import subprocess, sys, time\nfrom pathlib import Path\n"
        "def test_child():\n"
        f"    child = subprocess.Popen([sys.executable, '-c', {code!r}], start_new_session={escaped!r})\n"
        f"    Path({str(run.pids)!r}).write_text(str(child.pid))\n"
        f"    ready = Path({str(ready)!r})\n"
        "    deadline = time.monotonic() + 1\n"
        "    while not ready.exists() and time.monotonic() < deadline: time.sleep(0.01)\n"
        "    assert ready.exists()\n"
        + ("    time.sleep(30)\n" if stall else "")
    )


@pytest.mark.parametrize("stall", [False, True])
def test_owned_term_resistant_descendant_is_killed_without_touching_unrelated(control, stall):
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        run = control()
        (run.directory / "test_control.py").write_text(_spawn_source(run, resistant=True, stall=stall))
        run.start().finish()
        assert run.process.returncode == (124 if stall else 70), run.text
        assert run.result["reason"] == ("phase_timeout" if stall else "surviving_group_members")
        assert run.result["cleanup"]["kill_sent"] is True
        assert run.result["cleanup"]["complete"] is True
        assert not _alive(int(run.pids.read_text()))
        assert unrelated.poll() is None
    finally:
        _kill_owned(unrelated.pid, group=True)
        unrelated.wait(timeout=2)


def test_term_resistant_pytest_itself_is_killed(control):
    source = (
        "import signal, time\n"
        "def test_resistant():\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    time.sleep(30)\n"
    )
    run = control(source).start().finish()
    assert run.process.returncode == 124
    assert run.result["child_exit_code"] == -signal.SIGKILL
    assert run.result["cleanup"]["kill_sent"] is True
    assert run.result["cleanup"]["complete"] is True


def test_zombie_only_group_is_observed_clean_and_reaped(control):
    source = (
        "import os, signal, subprocess, sys, time, run_tests\n"
        "def test_zombie_group():\n"
        "    child = subprocess.Popen(['/bin/sleep', '.01'], start_new_session=True)\n"
        "    try:\n"
        "        deadline = time.monotonic() + 2\n"
        "        while time.monotonic() < deadline:\n"
        "            status = subprocess.run(['ps', '-p', str(child.pid), '-o', 'stat='],\n"
        "                capture_output=True, text=True, timeout=1).stdout.strip()\n"
        "            if status.startswith('Z'): break\n"
        "            time.sleep(.01)\n"
        "        assert status.startswith('Z')\n"
        "        probe_denied = False\n"
        "        try: os.killpg(child.pid, 0)\n"
        "        except PermissionError: probe_denied = True\n"
        "        except ProcessLookupError: pass\n"
        "        result = run_tests.cleanup(child, .2, .4)\n"
        "        assert result['complete'] is True\n"
        "        assert child.returncode == 0\n"
        "        if probe_denied:\n"
        "            assert any(error['operation'] == 'group_probe' and error['errno'] == 1\n"
        "                for error in result['errors'])\n"
        "    finally:\n"
        "        try: os.killpg(child.pid, signal.SIGKILL)\n"
        "        except (ProcessLookupError, PermissionError): pass\n"
        "        child.wait(timeout=1)\n"
    )
    run = control(source).start().finish()
    assert run.process.returncode == 0, run.text
    assert run.result["cleanup"]["complete"] is True


def _deny_supervisor_group_signals(signals, error_code=1):
    # Inject only into the supervisor; the child and finally cleanup remain real.
    return (
        "import errno, os, signal\n"
        "if '_REFRACT_TEST_GUARD' not in os.environ:\n"
        "    original_killpg = os.killpg\n"
        "    def denied_killpg(pgid, signum):\n"
        f"        if signum in {signals!r}:\n"
        f"            raise OSError({error_code!r}, 'synthetic signal error')\n"
        "        return original_killpg(pgid, signum)\n"
        "    os.killpg = denied_killpg\n"
    )


def test_permission_denied_live_group_cannot_be_reported_clean(control):
    run = control(
        "import time\ndef test_live(): time.sleep(30)\n",
        sitecustomize=_deny_supervisor_group_signals([0, int(signal.SIGTERM), int(signal.SIGKILL)]),
    ).start().finish()
    assert run.process.returncode == 124
    cleanup = run.result["cleanup"]
    assert cleanup["complete"] is False
    assert run.result["pid"] in cleanup["remaining_pids"]
    assert {error["operation"] for error in cleanup["errors"]} == {
        "group_probe", "send_sigterm", "send_sigkill",
    }
    assert all(error["exception"] == "PermissionError" and error["errno"] == 1
               for error in cleanup["errors"])
    assert _alive(int(run.pytest_pid.read_text()))


def test_unknown_group_probe_error_cannot_turn_child_zero_into_success(control):
    run = control(sitecustomize=_deny_supervisor_group_signals([0], error_code=5)).start().finish()
    assert run.result["child_exit_code"] == 0
    assert run.process.returncode == 70
    assert run.result["reason"] == "group_inspection_failed"
    assert run.result["cleanup"]["complete"] is False
    assert run.result["cleanup"]["remaining_pids"] is None
    assert {tuple(error.values()) for error in run.result["cleanup"]["errors"]} == {
        ("group_probe", "OSError", 5),
    }


def test_failed_kill_preserves_successful_term_evidence(control):
    run = control(sitecustomize=_deny_supervisor_group_signals([int(signal.SIGKILL)]))
    (run.directory / "test_control.py").write_text(_spawn_source(run, resistant=True, stall=True))
    run.start().finish()
    cleanup = run.result["cleanup"]
    assert run.process.returncode == 124
    assert cleanup["complete"] is False
    assert cleanup["term_sent"] is True
    assert cleanup["kill_sent"] is False
    assert run.result["child_exit_code"] == -signal.SIGTERM
    assert int(run.pids.read_text()) in cleanup["remaining_pids"]
    assert any(error["operation"] == "send_sigkill" and error["errno"] == 1
               for error in cleanup["errors"])


def test_escaped_output_holder_cannot_hold_supervisor_open(control):
    run = control()
    (run.directory / "test_control.py").write_text(_spawn_source(run, escaped=True))
    run.start().finish()
    assert run.process.returncode == 0, run.text
    assert run.elapsed < 3
    # The documented limit is intentional; fixture cleanup owns this control PID.
    assert _alive(int(run.pids.read_text()))
    assert run.result["cleanup"]["complete"] is True


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_supervisor_interrupt_still_cleans_owned_group(control, sig):
    run = control()
    (run.directory / "test_control.py").write_text(_spawn_source(run, resistant=True, stall=True))
    run.start()
    _wait_until(lambda: run.pids.exists() and (run.directory / "child-ready").exists())
    run.process.send_signal(sig)
    run.finish()
    assert run.process.returncode == 128 + sig
    assert run.result["reason"] == "interrupted"
    assert run.result["cleanup"]["complete"] is True
    assert not _alive(int(run.pids.read_text()))


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "true", "false", "no", "1e999"])
def test_invalid_budgets_are_rejected_before_child(control, value):
    run = control().start(extra=("--phase-timeout", value))
    run.process.wait(timeout=3)
    assert run.process.returncode == 2
    assert not run.output.exists()
    assert not run.pytest_pid.exists()


def test_diagnostic_budget_must_precede_phase_timeout(control):
    run = control().start(extra=("--diagnostic-after", "2", "--phase-timeout", "1"))
    run.process.wait(timeout=3)
    assert run.process.returncode == 2
    assert not run.pytest_pid.exists()


def test_unknown_guard_option_is_rejected_before_child(control):
    run = control().start(extra=("--phase-timout", "1"))
    run.process.wait(timeout=3)
    assert run.process.returncode == 2
    assert not run.output.exists()
    assert not run.pytest_pid.exists()


def test_reused_nonempty_directory_is_rejected(control):
    run = control().start().finish()
    original = (run.output / "result.json").read_bytes()
    run.start()
    run.process.wait(timeout=3)
    assert run.process.returncode == 2
    assert (run.output / "result.json").read_bytes() == original


def test_distinct_runs_have_distinct_execution_identity(control):
    first = control().start().finish()
    second = control().start().finish()
    assert first.process.returncode == second.process.returncode == 0
    assert first.result["execution_id"] != second.result["execution_id"]


def test_guard_identity_excludes_parameters_environment_and_outside_parents(control):
    secret = "PARAMETER_VALUE_SENTINEL"
    env_secret = "ENVIRONMENT_VALUE_SENTINEL"
    source = (
        "import pytest\n"
        f"@pytest.mark.parametrize('value', ['{secret}'], ids=['{secret}'])\n"
        "def test_parameter(value): pass\n"
    )
    run = control(source).start(env={"GUARD_SENTINEL": env_secret}).finish()
    assert run.process.returncode == 0, run.text
    generated = ((run.output / "progress.json").read_text()
                 + (run.output / "result.json").read_text() + run.text)
    assert secret not in generated
    assert env_secret not in generated
    assert str(run.directory) not in generated
    assert run.result["last_progress"]["test"] == {
        "file": "test_control.py", "class": None, "function": "test_parameter", "ordinal": 1,
    }
