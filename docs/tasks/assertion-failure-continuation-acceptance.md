# Assertion-failure continuation: local acceptance

Date: 2026-10-17. Result: **PASS for the bounded local task**.
Specification: [Continue after assertion failures](assertion-failure-continuation.md).
Starting and remaining HEAD: `d2a5ed9e8886ca54eff76b567c157875df6c3ca8`.
No submission was authorized or performed. Changes remain unstaged and uncommitted.

## Delivered behavior

- Keep `schema_version: 1`; ordinary assertion FAILED continues by default.
  Optional literal leaf `on_failure: stop` stops the rest of that projection.
- Missing, null, or unusable response references atomically BLOCK the consumer
  before its action. Independent later steps can run. Unexpected execution errors
  and SKIPPED still stop; there is no recovery/retry/session policy expansion.
- Backend and the shared UI loop use one continuation policy. One-level,
  same-actor inclusion preserves child leaf policy and qualified identities.
  Available named results remain usable after ordinary child FAILED.
- Reports retain failures, list preceding failures and blocking sources, and
  record value-free response/reference provenance. BLOCKED without a prior failure
  makes a domain DEGRADED, not PASSED. Actual binding values remain sensitive.
- Poll FAIL can supply its last actual response, explicitly timed out/non-final.
  Contract still requires final evidence; mock queues are not skipped or reordered.
- Minimal normalization-result validation prevents malformed port output from
  producing a pass. Contract preserves provider-build exceptions as ERROR reports.
- Waiting distinguishes its own expired budget from a port or nested wait failure.
  An execution timeout is ERROR, not a recoverable FAILED with stale response data.

The runnable [Documents example](../../examples/documents/scenarios/continue_after_failure.yaml)
creates a document, checks the actual list, and deletes by the returned ID.
Both response-only and persisted-title faults are detected; subsequent actions
really run when possible, without erasing the failed result. Real Chromium mock
and live tests likewise execute the subsequent action, or stop when requested.

## Sample and review decisions

All 19 maintained Scenario YAML files under `scenarios/` and `examples/` validate
with format 1. There was no maintained format-2 sample to migrate; format 2 was
only an unimplemented discussion proposal. No business assertions were changed
to make existing examples pass and no blanket stop policy was added.

Current documentation and runtime tests now describe the new behavior. Frozen
review-exercise YAML and sidecars, fault harness and historical result JSON, and
prior task/acceptance records remain byte-for-byte unchanged. Fixed faults still
have the same detected checks; current flat/include execution is compared with
each other rather than demanding old fail-fast action counts.

Keeping format 1 does not imply behavioral compatibility across engine revisions.
Review stopping intent and retain the engine revision with evidence. Content
pins do not pin execution semantics or prove renewed approval.

## Verification

Commands below run from the public repository root. All final checks exited 0.
Loopback bypass variables are command-scoped, not machine configuration changes.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest` | 1426 passed, 1 existing Starlette/httpx deprecation warning, no skips; 144.76 s |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 "$CORE_ENV/bin/python" -B -m pytest` | 1282 passed, 1 optional Demo collection skip; 33.83 s |
| `uv run --locked --no-sync python -B -m pytest tests/test_failure_continuation.py tests/test_asyncwait.py tests/test_documents_failure_continuation.py tests/test_scenario_contract_doc.py -o addopts='' -q` | 97 passed |
| Independent related suite plus additional probes | 571 passed, including 27 temporary independent probes |
| Independent timeout-focused subset | 105 passed: 72 continuation tests, 6 wait-helper tests, 27 independent probes |
| Independent `tests/demo/test_demo_failure_continuation.py` | 4 real Chromium tests passed, no skips |
| Consumer real Chromium/HTTP focused tests | 24 passed; final include-browser migration additionally passed its focused test |
| Maintained Scenario loading and format checks | 19 passed; authoring case inputs are not counted as Scenario files |
| `uv lock --check` | passed, lock unchanged |
| `bash scripts/check_repository_hygiene.sh` | passed |
| `git diff --check` and `git diff --cached --check` | passed; index empty |

`CORE_ENV` denotes an existing isolated Python 3.12 editable dev-only environment.
The acceptance check verified pytest/PyYAML present and Playwright, FastAPI,
httpx, and uvicorn absent. The optional Demo skip is not a substitute for the
full suite's real-browser checks.

Independent audit used a separate read-only reviewer, not either developer.
The 27 extra probes were in one temporary file, not a shipped checkout asset.
The following is the actual final command with local paths normalized; it needs
that retained audit file and is not a promise of checkout-only reproducibility:

```bash
PYTHONPATH="$PWD" uv run --locked --no-sync python -B -m pytest -q -o addopts='' \
  tests/test_failure_continuation.py tests/test_asyncwait.py \
  tests/test_documents_failure_continuation.py tests/test_scenario_contract_doc.py \
  tests/test_scenario_include.py tests/test_scenario_named_results.py \
  tests/test_frontend_stepwise.py tests/test_e2e_stepwise.py \
  tests/test_http_status_assertions.py "$AUDIT_DIR/test_audit.py"
```

Coverage includes local dependency chains, include arguments/results, policy
visibility in expansion/impact inspection, strict value handling, atomic binding
diagnostics, mock consumption, sensitive repr, context closure, real subsequent
traffic, error stopping, and polling/contract evidence provenance.

### Findings and reruns

Baseline red tests demonstrated old default blocking and rejection of the new
policy (two core tests and four consumer cases). They passed after implementation.

Independent audit found that malformed normalized fields could pass when only the
success flag was checked. Shared minimal port-result validation closed this gap
across backend, polling, live/mock UI and contract, with negative/positive tests.
No business response schema or adapter-certification system was introduced.

Timeout probes also showed that generic TimeoutError could be mistaken for the
outer polling deadline. A dedicated budget exception alone was insufficient:
a port could legitimately use the same waiting helper internally. Callback
timeouts are now kept separate from the current wait's own budget. Actual nested
wait probes, including clock and sleep callbacks, failed before the fix and pass
after it. Safe constant diagnostics avoid copying nested exception values.

Intermediate broad runs exposed old fail-fast expectations (13 offline cases,
plus one browser include case). These tests were updated to assert the new actual
actions and retained failures, not weakened to accept either outcome. An earlier
exploratory run was interrupted while loopback traffic used the environment's
proxy; it is not counted as a completed gate. Only the final stable reruns above
support acceptance.

## Accepted file scope

- Current docs: `SCENARIO.md`, `docs/browser-support.md`, `docs/onboarding.md`,
  `docs/roadmap.md`, and this task's specification/acceptance pair.
- Core: `refracto/asyncwait.py`, `refracto/normalization.py`,
  `refracto/contract/store.py`, `refracto/declaration/{binding,expansion,loader,model}.py`,
  `refracto/projection/{backend,contract,continuation,ui_stepwise}.py`, and `refracto/report.py`.
- New example: `examples/documents/scenarios/continue_after_failure.yaml`.
- New tests: `tests/test_failure_continuation.py`,
  `tests/test_documents_failure_continuation.py`, `tests/demo/test_demo_failure_continuation.py`.
- Existing tests: `tests/test_action_core.py`, `tests/test_backend_resolved_bindings.py`,
  `tests/test_collection_matching_count.py`, `tests/test_e2e_stepwise.py`,
  `tests/test_field_absent.py`, `tests/test_frontend_stepwise.py`,
  `tests/test_http_status_assertions.py`, `tests/test_http_status_consumers.py`,
  `tests/test_include_fault_controls.py`, `tests/test_projection_backend.py`,
  `tests/test_scenario_contract_doc.py`, `tests/test_scenario_include.py`,
  `tests/test_scenario_named_results.py`, `tests/test_scenario_review_exercise.py`,
  `tests/test_second_adapter.py`, and
  `tests/demo/{test_demo_http_status,test_demo_include,test_demo_review_exercise}.py`.

Public sources are the existing core, Demo/Documents reference applications, and
approved neutral behavior requirements. New and modified content was reviewed
for source neutrality, including untracked files not covered by tracked-file
hygiene alone. There are no private paths, products, measurements, or evidence.
No workroom access or modification occurred. Adapters, ports, MANIFESTO, BRAND,
Logo assets, existing maintained YAML and frozen history were not changed.

## Limits and stop point

This proves the bounded execution capability in synthetic reference consumers,
not real-product adoption value, human review savings, complete business coverage,
or independent evidence merely because multiple projections exist. No guaranteed
finally/cleanup, multi-user sessions, deeper inclusion, or automatic retry was
added. ERROR/SKIP recovery remains outside this slice.

Architect acceptance is local only. HEAD and local origin/main remain equal,
the index is empty, and no branch, commit, push, PR or merge was created for this
task. A separately authorized submission must review this exact scope again.
