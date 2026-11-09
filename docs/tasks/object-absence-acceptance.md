# Exact-ID object absence verification

Specification: [exact-ID absence](object-absence.md), approved 2026-11-09.
Starting main: `c9410f5df3c1d798dbebff3f809385a339f0a585`.
Status: PASS. Development, independent audit and architect acceptance passed on
2026-11-09 after the frozen-code regressions below. The maintainer authorized
task-branch submission after these gates. Hosted delivery is recorded separately
by the associated PR/commit history.

## Behavior and retained scope

Only `expect.backend_state.object_absent` is added. It accepts a business object
and an existing referenced ID. Complete zero matches pass; one surviving object
fails; incomplete, malformed, stale, ambiguous or failed acquisition errors.
An unavailable probe degrades visibly and an unavailable selector blocks its
consumer before the action. Step ERROR still aggregates under the existing
report rules; no new status or permissive passed gate is introduced.

The existing probe receives no expectation. Absence-only queries request no
fields but still perform a lookup. Mixed equality/absence checks for the same
strictly typed ID share a snapshot and requested-field union; neither is dropped.
Backend and live e2e share evaluation. Frontend and contract never query storage.
Existing trace state, user/session identity, polling, include results, Flow,
failure continuation and evidence copying remain intact. Format 1, one-level
inclusion and Python port signatures are unchanged.

The public SQLite consumer creates, independently verifies committed existence,
then deletes the actual ID and independently verifies absence. It uses a separate
read-only connection and checks that observation leaves the database unchanged.
Successful no-op deletion, uncommitted deletion and wrong-target deletion fail
despite HTTP 204. An always-empty reader or the wrong empty database fails the
preceding existence control. Query denial and incomplete results error instead
of proving absence. A second synthetic Documents consumer checks string IDs and
surviving soft-deleted objects without changing that target or its adapter.

This proves the stated local mechanism, not arbitrary adapter honesty, all
database types, production adoption, future absence or all caches/replicas.
Permission-filtered empty views are not storage proof. Unknown-ID denied creates,
asynchronous waiting, new selectors and a storage query DSL remain out of scope.

## Independent audit and corrected test oracles

Independent review passed 82 additional controls plus 194 new repository cases:
276 passed in 0.67 seconds. It exercised invalid empty observations, exact query
identity, contradiction grouping, copied sensitive evidence, safe errors, API/UI
projection boundaries, includes/results, Flow handoff and polling. No unresolved
production finding remained. The independent reviewer ran the public example;
create, verify_exists and delete passed with exit 0.

Initial new test fixtures exposed unsupported YAML aliases and a helper argument
collision. Tests were corrected, not the declaration rules. A new-test oracle
also incorrectly expected aggregate ERROR instead of the existing FAILED report
containing a step ERROR; audit verified the corrected distinction without any
production aggregation change. The example's middle step ID was aligned with
the approved `verify_exists` spelling before the final implementation freeze.

Developer core regression: 372 passed across new absence and existing equality
tests. Consumer regression: 44 passed across new SQLite/Documents and existing
SQLite tests. Documentation/example inventory, minimal onboarding and import
direction litmus: 72 passed. These overlapping panels are not additive totals.

## Reproducible commands

Run from the public repository. Guard output directories must be fresh.

```sh
python -m pytest tests/test_object_absence_declaration.py tests/test_object_absence_runtime.py tests/test_object_absence_sqlite.py tests/test_object_absence_documents.py -o addopts='' -q
python -m examples.sqlite_records.run
python -m pytest tests/test_stabilization_documentation.py tests/test_minimal_onboarding.py tests/test_opensource_litmus.py -o addopts='' -q
python scripts/run_tests.py --output-dir /tmp/object-absence-full -- -o addopts='' -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Dev-only checks use separate Python 3.11/3.12 environments with only `.[dev]`,
the same guarded entry and a 600-second suite budget. Optional browser collection
is excluded there; this is not evidence of browser execution. Both frozen-code
runs passed 5139 tests with one optional collection skip each: Python 3.11 in
42.86 seconds and Python 3.12 in 42.68 seconds. Each guard exited 0 with complete
cleanup and no diagnostic request. Hosted PR checks,
main checks and branch cleanup are separate delivery evidence in Git history.

The final guarded full suite passed 6384 tests with zero skips and one existing
third-party Starlette/httpx deprecation warning in 1120.85 seconds. Guard exit
was 0 with complete cleanup and no diagnostic request. Frozen implementation,
test and example hashes remained unchanged. Lock, hygiene and diff checks
passed; final documentation changes only record these results and acceptance.

## Information-source review

Inputs are the approved public capability, public code and neutral synthetic
Records/Documents consumers. Public documentation is English. No private
workspace, product, company, internal data, source snapshot or local evidence
was accessed or copied. No dependency, CI workflow, browser transport, original
Scenario or include pin changed. The assertion is the sole vocabulary addition.
