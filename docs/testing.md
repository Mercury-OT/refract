# Running the repository tests

The repository's guarded test entry runs pytest in a separate POSIX process
group and records which test and phase are active. It is test infrastructure;
it does not change Scenario YAML, assertions, product deadlines or RunReport.
Linux and macOS are supported. Run from a checkout with the desired test extras
and Chromium installed when browser tests are selected.

```sh
uv run --locked --no-sync python scripts/run_tests.py --output-dir /tmp/refract-check-001 -- -q
```

Choose a new output directory for each invocation. An existing nonempty directory
is rejected. Arguments after `--` are ordinary pytest arguments; for example,
selecting a file is useful locally, but the full CI suite has no selection filter.
Plain `pytest` still works and retains its previous behavior; it does not have
this external execution guard.
Use plain pytest for metadata commands such as `pytest --version`: a zero exit
before the progress plugin loads is not a completed guarded test run.

## Budgets and outcomes

The default diagnostic delay is 120 seconds in one phase, the phase stop budget
is 300 seconds, and the whole subprocess ceiling is 2700 seconds. Override these
with `--diagnostic-after`, `--phase-timeout` and `--suite-timeout` when justified.
All must be positive finite numbers; diagnostic delay must be below the phase
stop budget. A suite ceiling may be shorter than either phase threshold.
Termination adds at most 0.1 seconds for requested stack capture, followed by
two seconds for TERM and two seconds for KILL by default. The latter two are
explicitly configurable with `--terminate-grace` and `--kill-grace`. Each process-
group inspection has a one-second bound and may overrun the enclosing grace by
up to one second. Timeout controls allow a ten-second cleanup margin with these
defaults under normal OS scheduling; this is not a hard real-time guarantee.

The external monotonic clock cannot be reset by a test's fake application clock.
Setup, test call, fixture teardown, collection and finalization are included.
Progress resets the phase budget, not the whole-run ceiling. An ordinary pytest
failure remains a failure. A timeout, broken guard record, interrupted execution
or leftover owned process cannot become a successful result, even if pytest
prints passing assertions. There is no automatic retry or excluded slow test.

## Retained evidence

The output directory contains current progress, a final launcher result, raw
pytest output and requested Python stack diagnostics. Periodic status messages
identify the active file/function and phase without parameter values. Stacks
show call locations, not locals. Missing or unavailable diagnostics are recorded
honestly; they do not prevent the supervisor from enforcing its deadline.

Read `result.json` first, then `progress.json`, `pytest.log` and `stacks.log`.
These are launcher diagnostics, not business acceptance reports. Raw pytest
output and stack paths are not a general redaction system; review them before
sharing. Local runs never upload their output automatically.

CI uses suite ceilings of 120 seconds for litmus, 600 seconds for core, and the
2700-second default for the full suite. These do not alter the tests' product
deadlines. CI uses distinct output directories and attempts to
retain diagnostics for seven days after success or failure. Its job ceilings
also cover setup and upload. Complete optional browser tests remain required.

## Cleanup and limits

The supervisor requests stacks only from its ready pytest process, then performs
bounded cleanup of its own process group when needed. It does not kill processes
by name or touch another browser. Child output goes to a regular file: a child
retaining an output handle cannot keep the supervisor waiting for pipe EOF.
Cleanup checks live group members; zombie-only entries cannot execute or hold
output descriptors and are not reported as running children.
An operating-system permission response is not proof that a group is empty.
Bounded process inspection must establish that no live owned member remains.
Partial cleanup actions and errors retain the operation, exception type and
error number, without exception messages; failed inspection cannot count as clean.

A descendant that creates another session can escape group cleanup. This is not
a sandbox or a guarantee that every descendant is reclaimed. Disposable CI
workers supply the final host boundary. A dead host, forced termination or
uninterruptible operating-system work can also prevent a final stack/result.
Do not interpret the guard as proof that an earlier unexplained hang was fixed.

See the [bounded specification](tasks/test-execution-guard.md) for controls and
the information boundary. Scenario expressions and product execution remain
governed by [SCENARIO.md](../SCENARIO.md).
