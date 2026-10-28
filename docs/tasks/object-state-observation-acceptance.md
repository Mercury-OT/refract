# Read-only object-state observation: acceptance evidence

## Scope

Local architect acceptance **PASS**, 2026-10-28, against public main `52332e7` and the
[approved specification](object-state-observation.md). The maintainer separately
authorized submission on 2026-10-29; hosted checks, merge and cleanup remain
publication gates. The approved declaration remains `schema_version: 1`, with one-level
include and the existing users, sessions, references and continuation policy.

The new `backend_state.object_field_equals` assertion compares actual business
object fields through an optional, separate `ObjectStateProbe`. SQL, storage
schema and connection settings stay in adapter wiring. Existing trace/span
`StateProbe` behavior is unchanged. No database, cache or log query language,
requestless observation, polling-until-match, Flow, UI editor or private-product
integration is included.

## Actual storage controls

The complete approved [create/read Scenario](../../examples/sqlite_records/scenarios/create_and_verify_storage.yaml)
runs against a stateful, in-process Records API backed by a real temporary SQLite
database. After its real GET response, a separate connection opens the database
with `mode=ro` and `query_only`. One parameterized SELECT supplies both requested
fields from one snapshot. Observation does not share the API writer connection.

| Control | API observations | Storage observation | Result in backend and API e2e |
| --- | --- | --- | --- |
| Normal committed create/read | 201 then 200, actual created ID | Exactly that record, expected code and name | PASSED, no degradation. |
| Writer returns success without committing | 201 then 200; writer's own GET can see the row | Separate reader sees no committed object | Both object checks FAILED. |
| Writer commits an incorrect name | 201 then 200, correct ID | Code matches; actual stored name differs | Name check FAILED; code check passes. |
| Reader opens a database without the required table | 201 then 200 | Real SELECT raises | Step ERROR; no fabricated absence or passed state check. |

Tests assert query reachability after both actions, independent connections, one
SELECT for two fields, exact returned ID, source and execution attribution,
unchanged database bytes during observation, and connection cleanup. Contract
reuses backend recordings without issuing another storage query, and explicitly
lists the object checks outside its scope. The example command exits zero only
on the strict `PASSED` status:

```sh
uv run --frozen python -m examples.sqlite_records.run
uv run --frozen refracto validate examples/sqlite_records/scenarios/create_and_verify_storage.yaml
```

Observed example result: PASSED, with both create and read PASSED. Validation
finds two requests, five response checks and two state checks. These are local
SQLite and in-process API results, not browser or production storage evidence.

## Bounded declaration and execution checks

The three new test files collect 222 cases: 119 declaration, 91 runtime and 12
SQLite integration cases. They cover:

- Exact assertion keys; literal business names; strict integer/string referenced
  IDs; scalar expected values; invalid known inputs and response-derived values;
  inclusion overrides, named results and existing member references. Direct
  `concat` is rejected here; referencing a composed parameter remains allowed.
- Selector-only immutable query shape; no expected data or unrelated bindings;
  one query per object and exactly typed ID; fresh observation identity; strict
  query echo, source, completeness, object count, fields and finite data.
- Complete absence or inequality as FAILED; query/malformed/incomplete evidence
  as ERROR; unavailable dependencies as BLOCKED before action; missing probe as
  visible degradation. Null differs from absence, and bool differs from int.
- Copied snapshots and hidden-by-default sensitive evidence, safe acquisition
  errors, and preservation of earlier observations when a later query errors.
- Existing ordinary-failure continuation and explicit stop, terminal-only API
  polling, user/session renewal and include mappings. Backend, API e2e and the
  scripted live-UI path use the same evaluator. Frontend and contract do not
  query storage, including contract EMPTY and error paths.

```sh
uv run --frozen pytest -o addopts='' -q \
  tests/test_object_state_declaration.py \
  tests/test_object_state_runtime.py tests/test_object_state_sqlite.py
```

Development also ran 646 focused tests across the new suites and existing
action-port, backend, e2e stepwise, contract, execution-boundary, continuation and
user/session tests; all passed. No additional test framework or dependency was
added.

## Independent review and regression gates

Separate reviewers, neither the relevant developer, reviewed the declaration
and SQLite slices. Declaration review passed 522 focused/regression tests and
30 independent adversarial probes, including include substitutions and precise
dependency attribution. SQLite review reran all 12 integration tests and the
example, then passed seven independent checks covering literal SQL-special data,
URI-safe file names, exact mappings, real absence, read-only protection, error
cleanup and selector-only port fields. The declaration review's documentation
clarification about direct `concat` has been incorporated.

Runtime independent review also passed: 442 focused/legacy tests and 21 additional
adversarial probes checked capability gaps, malformed/stale facts, pre-action
dependency blocking, selector-only inputs, snapshot ownership, user/session and
projection identity, and live UI error cleanup. No blocking findings remained.
If a later object lookup errors, earlier snapshots remain available but the
partially accumulated object-check list is omitted; the step is ERROR and the
strict run cannot pass. No partial-success claim is made.

| Verification | Actual result (exit 0) |
| --- | --- |
| `uv run --frozen pytest -o addopts='' -q` | 4541 passed, one existing third-party deprecation warning, 491.88 seconds. Sequential full suite includes the existing real-browser and demo regressions. |
| Three new test files, command above | 222 passed. |
| Offline core suite, Python 3.11.15 and 3.12.13 with dev extra only | 3964 passed, 1 skipped in each. No optional browser/demo packages required. |
| `uv run --frozen pytest -o addopts='' -q tests/test_opensource_litmus.py tests/test_stabilization_documentation.py tests/test_stabilization_boundaries.py` | 90 passed. The example inventory now has 25 runnable linked YAML files. |
| `uv lock --check` | Passed; dependency files unchanged. |
| Repository hygiene, independent new-file source scan, diff and cached-diff checks | Passed; temporary database paths and sensitive driver output are not public evidence. |

All local gates passed. The new state-observation live-UI tests use scripted
evidence; the existing real-browser tests provide regression coverage, not a new
browser-to-SQLite integration claim. Independent documentation review reran the
example, validation and 45 documentation sentinel tests, and found no blocking
conflicts. Minor wording clarifications were incorporated without changing YAML
or runtime behavior.

## Accepted file scope and repository boundary

At local acceptance, the accepted changes comprised 15 modified tracked files
and 14 new files:

- Declaration: `refracto/declaration/{binding,loader,vocabulary}.py` and new
  `refracto/declaration/object_state.py`.
- Execution and evidence: `refracto/{ports,runner,report}.py`, new
  `refracto/object_state.py`, and
  `refracto/projection/{backend,contract,e2e,ui_stepwise}.py`.
- Consumer: the new `adapters/sqlite_records/{__init__,adapter}.py` and
  `examples/sqlite_records/{__init__,app,run}.py`, its README and
  `scenarios/create_and_verify_storage.yaml`.
- Tests: new `tests/test_object_state_{declaration,runtime,sqlite}.py` and the
  updated `tests/test_stabilization_documentation.py` example inventory.
- Documentation: `SCENARIO.md`, `docs/{onboarding,roadmap,threat-model}.md`, this
  acceptance record and `docs/tasks/object-state-observation.md`.

Comparison with the starting 380 tracked-file hashes leaves 365 unchanged.
All existing YAML and include locks, production adapters, dependency files, CI,
MANIFESTO and BRAND are byte-identical. Source review used public code and neutral
synthetic examples only. At local acceptance, the index was empty and HEAD and
local origin/main were
`52332e720170933c4b34eb6d99208ac9a4b76eb9`. No branch, commit, push, PR or merge was
performed at that acceptance gate. The subsequently authorized task PR records
hosted delivery; local checks alone do not prove completion of that workflow.

## Submission follow-up: browser test budget

The first PR run on `871b9bc` failed one existing browser boundary test; the
branch-push full suite on the identical commit passed. The failure had no HTTP
requests and an empty assertion-localization list. That output did not retain
step errors, so it cannot uniquely establish the hosted failure's root cause.

Thirty separate local executions of the same live case passed. A controlled
two-second Chromium startup delay reproduced the visible symptoms with the
test's 1500 ms budget: open ERROR, following steps BLOCKED, no HTTP request. With
5000 ms, the same control completed the real flow and both API requests. This
demonstrates a reachable startup-budget weakness, not proof of the original
hosted cause.

The supplemental fix is limited to `tests/browser/test_action_port_boundary.py`:
use BrowserSupport's normal 5000 ms budget for this non-performance test and
include step status/detail in assertion failure diagnostics. No assertion,
negative control, production timeout, core behavior or YAML is weakened or
changed. The six-case browser file passes; the modified original test also
passes with the controlled startup delay. Independent review reran all six cases
without skips and passed; architect acceptance includes this bounded CI repair.
Renewed hosted checks remain required before merge. This adds one test file to the original
29-file submission scope; all other supplemental edits are this evidence record.

## Limits

The source label, trace and echoed query provide local attribution, not external
authentication of the adapter or database. The separate SQLite connection proves
the selected current committed fields in this example. It does not prove their
entire causal history, future durability, a transaction across multiple objects,
or support for every database. No existing span or contract result is counted as
an independent storage observation.

Actual fields remain sensitive report data even though default representations
hide them. This task supplies no general serialization or safe-export system.
A faulty or hostile probe can still fabricate internally consistent facts; the
[threat model](../threat-model.md) describes that boundary. Adoption value,
maintenance cost and real-product acceptance require separate evidence.

No private workspace was accessed. All changes remained local and unstaged until
the separate submission authorization after final acceptance.
