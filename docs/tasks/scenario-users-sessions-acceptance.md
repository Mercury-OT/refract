# Scenario users and sessions: local acceptance

Date: 2026-10-17. Result: **PASS for the bounded local task**.
Specification: [Scenario users and sessions](scenario-users-sessions.md).
Starting and remaining HEAD: `95ba66d34589ef688b5d172301c64323a3de0762`.
Submission is not authorized. Changes remain unstaged and uncommitted.

## Delivered behavior

- Keep `schema_version: 1`. A required `users` list selects anonymous execution,
  a single default user, or explicit per-step selection from multiple users.
  Role declarations and the old YAML `actor` field are not accepted.
- Bind each logical user to a fixed, distinct account before business actions.
  Acquire sessions lazily and reuse them. A leaf `session: new` authenticates the
  same account again and replaces only that user's current session; it does not
  restore permissions or silently retry a rejected request.
- A single-user included child aliases its local user to the selected parent
  user without editing child bytes. Named results and reviewed byte pins remain.
  Anonymous inclusion remains anonymous. Multi-user child inclusion and deeper
  nesting are explicitly rejected.
- Backend and the single shared UI loop use the same session manager. UI contexts
  remain separate per current user/session. New authentication replaces only
  the selected context; all owned contexts close exactly once.
- Permits, UI evidence, recordings, and reports retain user/session attribution.
  Cross-user and stale-session evidence is rejected. Contract checks actual
  backend execution provenance without authenticating or sending requests.
- Ordinary assertion failure still continues unless the leaf requests stop.
  Execution errors and skips still stop; dependency-blocked consumers neither
  act nor authenticate. Sensitive authentication material stays out of default
  representations. Generic serialization is not a safe report export.

## Executed consumers and limits

The public synthetic [owner/peer example](../../examples/documents/scenarios/owner_peer.yaml)
creates through an included child, verifies the creator can read, verifies the
other authenticated account has the same observed role, and checks its 403.
The [permission/session example](../../examples/documents/scenarios/permission_sessions.yaml)
performs a real permission update, checks the old session, and authenticates the
same account again. Its approved target policy is immediate revocation.
A session-snapshot-policy negative control fails the old-session expectation
while still executing the new-session comparison; the final report stays failed.

The Documents target enforces its own account, ownership, and session policy in
process; responses are not generated from expectations. These are synthetic
capability checks, not evidence of real-product adoption or production security.

Real Chromium tests exercise separate cookies/local storage, preserved context
state when switching users, replacement of only one context, globally ordered
explicit mock consumption, and anonymous execution after authenticated execution.
The Demo does not enforce authorization: those browser results prove context and
evidence isolation, not access-control correctness.

Authenticator identity is an adapter claim validated for internal consistency,
not independent proof against a malicious adapter. There is no automatic refresh,
multiple retained sessions for one user, role provisioning, cleanup guarantee,
multi-user child inclusion, or new rejection-classification capability.

## Migration and review boundaries

All 23 maintained Scenario files under `scenarios/` and `examples/` load with
format 1 and explicit `users`. Current guides, reference authenticators, test
fixtures, and review-exercise YAML/pins were explicitly migrated. Existing
business checks were preserved. A current create/update/read parent replaces a
test's dependence on an old task-document snippet.

The frozen original include fault harness and its historical result JSON remain
unchanged, as do prior task/acceptance records. Current fault execution uses
explicitly migrated declarations, not silent conversion of historical YAML.
Updating a byte pin is not proof of renewed human approval or a new review-cost
measurement. The retained internal Python constructor layout is not a second
accepted YAML grammar and still undergoes runtime identity validation.

## Verification

Commands run from the public repository root. Final checks below exited 0.

| Check | Actual result |
| --- | --- |
| `NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 uv run --locked --no-sync pytest -o addopts='' -q --tb=short` | 1548 passed, 1 existing Starlette/httpx deprecation warning, no skips; 150.11 s |
| Same loopback bypass, `"$CORE_ENV/bin/python" -B -m pytest -o addopts='' -q --tb=short` | 1401 passed, 1 optional Demo collection skip; 34.55 s |
| `uv run --locked --no-sync pytest tests/test_scenario_contract_doc.py tests/test_include_documentation.py tests/test_minimal_onboarding.py tests/test_opensource_litmus.py -o addopts='' -q` | 24 passed |
| Maintained Scenario loading, format and user declarations | 23 files validated |
| CLI validation of both new Documents parent examples | passed |
| Final independent users/include/named-results/continuation regression | 341 passed |
| Independent `tests/demo/test_demo_user_contexts.py` | 3 real Chromium tests passed, no skips |
| Independent additional Recorder probes | 7 identity/order/count probes and 6 NaN/type/fidelity probes passed |
| `uv lock --check` | passed; lock unchanged |
| `bash scripts/check_repository_hygiene.sh` | passed |
| `git diff --check`, `git diff --cached --check` | passed; index empty |

`CORE_ENV` is a separately created Python 3.12 editable `.[dev]` environment.
PyYAML and pytest were present; Playwright, FastAPI, httpx, and uvicorn were absent.
Its optional Demo skip does not substitute for the full suite's browser checks.
Independent probes were temporary reviewer checks, not additional checkout tests.
The 341-test independent command used `tests/test_users_sessions_core.py`,
`tests/test_scenario_include.py`, `tests/test_scenario_named_results.py`, and
`tests/test_failure_continuation.py`. A separate broad reviewer run was stopped
to avoid duplicate work and is not counted as passed evidence.

### Findings closed before acceptance

Independent audit found that backend trusted Recorder readback: a modified user
or session generation could contradict the step report while backend passed.
Core now retains its own snapshots, validates each append and final read, checks
strict field types/content/count/order, and returns only verified copies.
Negative controls cover identity changes, bool/integer confusion, duplicate,
missing and reordered evidence, polling records, and post-run mutation.

Final regression exposed an important distinction: NaN is not equal to itself
for a business assertion, but its original observed bytes must remain recordable.
A recording-only comparator preserves its IEEE-754 representation without
changing assertion equality or reference-validity rules. The consumer still
blocks an invalid NaN reference. A prior contract-localization test now uses an
explicit offline drift copy rather than requiring a live Recorder to tamper
successfully; its original localization assertions remain intact.

Intermediate migration runs and the three-failure regression before this fix
are not acceptance evidence. The final full and isolated reruns above are green.
Independent audit and architect review found no remaining blocker.

## Accepted file scope

The following 118 paths are the bounded local task scope. A later submission
requires separate maintainer authorization and a fresh unexpected-change check.

```text
README.md
SCENARIO.md
adapters/demo/auth.py
adapters/demo/ui.py
adapters/documents/auth.py
adapters/documents/normalizer.py
adapters/documents/resolver.py
adapters/documents/wiring.py
docs/browser-support.md
docs/impact-review.md
docs/onboarding.md
docs/review-exercise/README.md
docs/review-exercise/baseline/child.yaml
docs/review-exercise/baseline/flat.yaml
docs/review-exercise/baseline/included.includes.json
docs/review-exercise/baseline/included.yaml
docs/review-exercise/case-01/child.yaml
docs/review-exercise/case-01/flat.yaml
docs/review-exercise/case-01/included.includes.json
docs/review-exercise/case-01/included.yaml
docs/review-exercise/case-02/child.yaml
docs/review-exercise/case-02/flat.yaml
docs/review-exercise/case-02/included.includes.json
docs/review-exercise/case-02/included.yaml
docs/review-exercise/case-03/child.yaml
docs/review-exercise/case-03/flat.yaml
docs/review-exercise/case-03/included.includes.json
docs/review-exercise/case-03/included.yaml
docs/roadmap.md
docs/tasks/scenario-users-sessions-acceptance.md
docs/tasks/scenario-users-sessions.md
examples/documents/app.py
examples/documents/scenarios/continue_after_failure.yaml
examples/documents/scenarios/create_list_delete.yaml
examples/documents/scenarios/http_status_create_delete.yaml
examples/documents/scenarios/owner_peer.includes.json
examples/documents/scenarios/owner_peer.yaml
examples/documents/scenarios/permission_sessions.includes.json
examples/documents/scenarios/permission_sessions.yaml
examples/documents/scenarios/rejected_create.yaml
examples/documents/scenarios/shared/create_document.yaml
examples/minimal/adapters.py
examples/minimal/scenarios/create_and_delete.yaml
examples/minimal/scenarios/state_degraded.yaml
examples/scenario-reuse/README.md
examples/scenario-reuse/create_read.includes.json
examples/scenario-reuse/create_read.yaml
examples/scenario-reuse/create_update_read.includes.json
examples/scenario-reuse/create_update_read.yaml
examples/scenario-reuse/shared/create_item.yaml
refracto/contract/store.py
refracto/declaration/expansion.py
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/ports.py
refracto/projection/backend.py
refracto/projection/continuation.py
refracto/projection/contract.py
refracto/projection/recording.py
refracto/projection/sessions.py
refracto/projection/ui_stepwise.py
refracto/report.py
refracto/runner.py
refracto_browser/_support.py
scenarios/demo_include_items.includes.json
scenarios/demo_include_items.yaml
scenarios/demo_include_items_ui.includes.json
scenarios/demo_include_items_ui.yaml
scenarios/demo_item_create.yaml
scenarios/demo_item_delete.yaml
scenarios/demo_item_e2e_stepwise.yaml
scenarios/demo_item_frontend_stepwise.yaml
scenarios/demo_item_list_after_create.yaml
scenarios/demo_item_update.yaml
scenarios/demo_job_run.yaml
scenarios/include_shared/create_item.yaml
scenarios/include_shared/create_item_ui.yaml
tests/browser/adapter.py
tests/demo/test_demo_failure_continuation.py
tests/demo/test_demo_include.py
tests/demo/test_demo_reuse_walkthrough.py
tests/demo/test_demo_review_exercise.py
tests/demo/test_demo_stepwise_e2e.py
tests/demo/test_demo_user_contexts.py
tests/fakes.py
tests/fixtures/include_demo_flat/items.yaml
tests/fixtures/include_demo_flat/items_ui.yaml
tests/fixtures/synthetic_scenario.yaml
tests/fixtures/synthetic_templated_scenario.yaml
tests/named_results_fault_controls.py
tests/test_action_core.py
tests/test_browser_user_bindings.py
tests/test_collection_matching_count.py
tests/test_contract.py
tests/test_declaration.py
tests/test_documents_users_sessions.py
tests/test_e2e_stepwise.py
tests/test_failure_continuation.py
tests/test_field_absent.py
tests/test_frontend_stepwise.py
tests/test_http_status_assertions.py
tests/test_http_status_consumers.py
tests/test_include_documentation.py
tests/test_include_fault_controls.py
tests/test_objects_matching_count.py
tests/test_projection_backend.py
tests/test_projection_e2e_contract.py
tests/test_projection_frontend.py
tests/test_scenario_contract_doc.py
tests/test_scenario_impact.py
tests/test_scenario_include.py
tests/test_scenario_named_results.py
tests/test_scenario_review_exercise.py
tests/test_second_adapter.py
tests/test_ui_users_sessions.py
tests/test_users_sessions_core.py
```

Public sources are existing core, Demo/Documents reference targets, and the
approved product-neutral behavior. New files were also checked for machine-local
paths, non-English text, and secret-like content; tracked-file hygiene alone
does not establish neutrality. No private source, schema, evidence, or internal
name was used. No workroom file was read or changed in this task.

No staging, commit, branch, push, PR, merge, or hosted CI was performed. Local
HEAD and the local origin/main reference remain equal to the starting commit.
This acceptance does not authorize submission or close unrelated roadmap work.
