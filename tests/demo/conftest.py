"""Starts examples/demo-app as a real local uvicorn *subprocess* (not an in-process
TestClient) so adapters/demo can exercise it over real HTTP — later tasks (Playwright
UiDriver) need a real running server too, so this fixture is shared infrastructure for
all of tests/demo/, not just the backend projection.

Subprocess over programmatic-uvicorn-in-a-thread: examples/demo-app is not a Python
package (hyphen in the dirname — see examples/demo-app/run.py's docstring), and
run.py already exists as a thin `uvicorn.run(app, host, port)` launcher accepting
--host/--port. Running it as `python run.py --port N` is the path of least resistance:
no sys.path surgery, no in-process app-module state to leak between tests, and it
matches how a real Playwright test would hit the app (a separate OS process).
"""
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Skip this whole directory cleanly when the `demo` extra is absent. A bare import here
# would raise during collection, which aborts the entire run rather than skipping these
# tests -- and the offline core job installs `dev` only, on purpose.
httpx = pytest.importorskip("httpx")

DEMO_APP_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "demo-app"
RUN_PY = DEMO_APP_DIR / "run.py"


def _free_port() -> int:
    """Ask the OS for a free ephemeral port, then release it immediately. There is a
    small window where another process could grab it before uvicorn binds — acceptable
    for a local test fixture; if this becomes flaky, retry-on-bind-failure would be the
    next step."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _read_log(log_file) -> str:
    log_file.seek(0)
    return log_file.read().decode(errors="replace")


def _wait_until_up(proc: subprocess.Popen, base_url: str, log_file, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"demo app subprocess exited early (code {proc.returncode}) before "
                f"accepting connections:\n{_read_log(log_file)}")
        try:
            httpx.get(f"{base_url}/", timeout=1.0)
            return
        except httpx.TransportError:
            time.sleep(0.1)
    raise RuntimeError(f"demo app never came up at {base_url} within {timeout}s:\n{_read_log(log_file)}")


@pytest.fixture
def demo_server():
    """Start the demo app on a free localhost port; yield its base_url; tear it down."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    # A real spooled file, not subprocess.PIPE: a pipe has a small OS buffer (~64KB) that
    # fills and deadlocks the child if nobody drains it while it's running — a real risk
    # here since later tasks (Playwright UI driving) reuse this fixture and will make this
    # process live longer and log more than this task's single POST.
    with tempfile.TemporaryFile() as log_file:
        proc = subprocess.Popen(
            [sys.executable, str(RUN_PY), "--host", "127.0.0.1", "--port", str(port)],
            stdout=log_file, stderr=subprocess.STDOUT,
        )
        try:
            _wait_until_up(proc, base_url, log_file)
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
