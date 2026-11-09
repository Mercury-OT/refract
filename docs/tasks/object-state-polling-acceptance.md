# Bounded object-state waiting verification

Specification: [object-state polling](object-state-polling.md), approved
2026-11-09. Starting main: `672f0c848954d8526be91f050f18c5631102b25e`.
Status: PASS. Development, independent audit and architect acceptance passed
on 2026-11-09 after the frozen implementation checks below. The maintainer
authorized submission and merge after acceptance and successful hosted checks.
Publication remains separately evidenced by the associated PR/commit history.

## Maintainer summary

- A single request can now be followed by bounded read-only object observations.
- Only explicit `object_poll: {on_timeout: FAIL}` enables this behavior.
- Complete mismatches retry; evidence errors stop, and late matches cannot pass.
- Real SQLite deletion and a second Documents update demonstrate the boundary.
- This does not cancel arbitrary blocked adapters or prove sustained state.

## Implemented boundary

Format 1, one-level inclusion, actions, probe signatures, assertion vocabulary
and report statuses are unchanged. One exact typed object identity is selected
before the action. Each attempt obtains a fresh core-owned snapshot; all object
conditions must hold together. The action and its HTTP recording are not
replayed. Missing capability degrades visibly; invalid selectors block before
effects; query/identity/completeness errors are ERROR rather than retries.

The caller's existing PollConfig supplies timeout and interval. Read duration
counts, sleeps are clamped, no read starts at the deadline, and a matching
result returned at or after it cannot pass. ObjectPollResult records configured
timing, attempts, elapsed time and outcome separately from HTTP attempts. A
prior response or UI check failure survives an eventual match. Ordinary
continue/stop and Flow publication behavior remain in force.

Backend and live e2e share the observer, including request-associated UI steps.
Frontend and contract do not query storage or claim to check this policy.
Existing one-shot object observations and GET polling remain unchanged.
Simultaneous GET polling, span checks, multiple objects, requestless waits,
SKIP and inline YAML budgets are rejected in this slice.

## Feasibility and real consumers

Before implementation, an exact-ID SQLite lookup under an exclusive lock raised
after its configured one-second busy wait (1.058 seconds observed). Three
distinct read-only connections, including the failed one, closed; subsequent
reads saw newly committed presence and deletion. The repository test repeats
this check with a broad scheduler allowance. A SQLite busy timeout bounds lock
waits, not arbitrary SQL execution; the demonstrated lookup uses a primary key.

The new public consumer creates, independently verifies existence, then sends
DELETE once with a 202 response. A separate target worker commits deletion;
the probe never drives target changes. Tests control worker release from the
host and observe present then absent through separate closed read connections.
No-op, wrong-object and uncommitted deletion time out. Query denial/incomplete
evidence error immediately. A failed response remains failed after actual
deletion. Without the policy the same target retains one-shot failure semantics.
The executable example uses a real worker and cleans up its resources.

A second synthetic Documents consumer uses string IDs and two state fields.
Its controls alternate matches between snapshots; those never satisfy the
combined expectation. This proves the bounded mechanism in these consumers,
not arbitrary adapter fidelity or production adoption value.

## Independent review and corrections

Independent review passed 39 additional adversarial controls, 134 task tests
and 63 documentation/litmus tests: 236 passed in 2.70 seconds. The reviewer also
ran the real example and CLI expansion successfully. A final addendum ran the
29 review-equivalence tests plus the independent controls: 68 passed in 1.11
seconds. These overlapping panels must not be summed as unique coverage.

One production finding was fixed before the final freeze: two distinct generated
parameter IDs could disagree after binding and produce ERROR instead of the
specified BLOCKED, although no action ran. Resolved selection conflicts now
block before effects. Contract independently reproduces that exact conflict
from frozen parameters before accepting a block with no earlier-step cause;
a counterfeit empty-cause block with valid selectors remains rejected.

The first dev-only suite found ten failures in an existing fail-closed Step
field inventory. The new field was added both to that inventory and to its
materialized semantic comparison; the guard was not relaxed. The then-running
full suite was interrupted with complete cleanup and rerun after this test
correction. No implementation changed during the final full/offline runs.

## Verification commands and results

Run from the public repository, with fresh guard output directories:

```sh
python -m pytest tests/test_object_poll_declaration.py tests/test_object_poll_runtime.py tests/test_object_poll_sqlite.py tests/test_object_poll_documents.py -o addopts='' -q
python -m examples.sqlite_records.run_async
python -m pytest tests/test_stabilization_documentation.py tests/test_scenario_review_exercise.py tests/test_opensource_litmus.py -o addopts='' -q
python scripts/run_tests.py --output-dir /tmp/refract-object-poll-full-final -- -o addopts='' -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

The final guarded full suite passed **6519 tests**, no skips, with one existing
third-party Starlette/httpx deprecation warning in **1121.48 seconds**. The guard
exited 0, requested no diagnostics and confirmed complete cleanup. Separate
Python 3.11/3.12 environments with only `.[dev]` each passed **5274 tests** with
one optional collection skip, in 44.69 and 45.53 seconds respectively, using
the same guarded entry with a 600-second suite budget. Optional collection
exclusion is not browser execution evidence; the full suite exercised Chromium.

Developer core regression passed 650 tests; consumer regression passed 29.
The final implementation, test and example hashes matched the reviewed freeze.
Lock, hygiene and diff checks passed. Closing documentation only records these
actual results. Hosted PR/main checks and branch cleanup remain distinct gates.

## Information sources and remaining limits

Public code and neutral Records/Documents examples are the only sources. No
private workspace, product, company data or evidence was accessed or copied.
Public text is English. No dependency, CI workflow, browser transport, original
Scenario, include pin, probe port or assertion vocabulary changed.

Synchronous probes cannot be forcibly interrupted. Adapters must bound reads
and release resources; core rejects late success without promising hard
cancellation. A successful wait proves one matching snapshot within the budget,
not continuous absence, later durability, every replica or causality. Reviewed
mapping and positive controls remain necessary; identity echoes and source
labels do not authenticate an adapter's claims.
