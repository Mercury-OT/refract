# Action-port boundary: local acceptance

Date: 2026-10-27. Independent audit: **PASS**. Architect acceptance: **PASS** for
the bounded task. Specification: [action-port boundary](action-port-boundary.md).
Starting main: `bb9c680ac68a4b3fb7fe5ce422807174edce569a`.
The maintainer approved implementation and the threat boundary, and explicitly
authorized submission after development, independent audit, and acceptance.
This record describes local evidence; hosted PR/main CI remains a separate gate.
No private workspace was accessed or modified.

## Delivered behavior

The request resolver receives only a prepared `RequestAction`: method, bound
logical path, body, query, and business headers. Browser opening receives session
and existing mode/context data. Primitive execution receives a permit and a
normalized tuple of business-header names for credential-collision checks.
Neither narrowed operation interface receives Scenario, Step, expectations, or
the complete resolved-binding map. Core retains comparisons and report bindings.

New request/action containers are detached from declarations and retained core
data. After validating the resolver result, core also owns a snapshot of that
result. This second boundary matters when a resolver reuses its input dictionaries
or retains its returned RequestSpec: later adapter callbacks cannot change a
future polling request or its comparison baseline through that alias.

Credentials and browser contexts retain their identity. Explicit mock fixtures
remain simulation inputs, and the shared run-local queue still uses one mutable
cursor across contexts; core retains an independent fixture plan. The three
narrowed callback boundaries report which operation failed without copying
arbitrary callback exception text into the report. Existing checks and states
remain unchanged. Legacy Python signatures fail visibly, without a retry that
restores declaration access. Public consumers and migration guidance are updated.

## Mechanical evidence

| Specification | Retained evidence |
| --- | --- |
| M1 | Exact RequestAction/permit/signature allowlists and actual-argument graph probes reject nested or repackaged assertion objects. The probes have deliberate failing inputs. |
| M2-M3 | Actual runner spies in backend, frontend and e2e exclude current/future/child expectation-only values and unused parameters. Prior response values used only by checks remain in core/report, not UI inputs. |
| M4 | Legitimate equal request/UI input and expectation values still reach the operation. Paired declarations change only checks: corresponding operation contents stay equal, while the wrong check fails. |
| M5 | Nested body/query/header and current/retained UI value mutations cannot rewrite declarations or retained evidence. Twelve backend/e2e polling cases cover resolver aliases changed during send or normalization. |
| M6 | Real browser request checks, credential collisions, absent/ambiguous primary traffic and query/body/header mismatches retain their existing behavior. Names-only input rejects wrong type/case/order/duplicates. |
| M7 | Actual mock/live tests preserve ordered explicit fixtures, shared cursor, multi-user/session behavior and no live fallback. An altered shared fixture cannot rewrite the retained validation plan. |
| M8 | Existing full regression covers continuation, blocking, polling, users/sessions, includes/results, run values, headers/query and contract reuse without extra requests. |
| M9-M10 | Sensitive repr/error controls, dev-only import/litmus checks, and visible old-signature failures pass. No compatibility retry adds an action or fabricates evidence. |

The focused modules are `tests/test_action_port_boundary.py` and
`tests/browser/test_action_port_boundary.py`. Existing behavior tests were
migrated to the new port calls; business checks, expected states, negative
controls and execution counts were not relaxed. Tests for the removed binding
map now establish that it is absent and that core still retains the same values.

During development, the twelve retained-resolver polling controls failed before
the returned-request snapshot was added, then passed. Independent review also
constructed backend and e2e probes that changed every retained RequestSpec field
and a parent-response/include/UI-check probe; all passed. These temporary probes
are additional review evidence, not an exhaustive input-space claim.
An intermediate migration touched an archived harness and triggered its existing
hash checks. The archived file was restored byte-for-byte; the maintained consumer
alone was migrated. Historical evidence hashes were not refreshed to hide it.

## Verification

All final verification commands below exited 0.
Local full environment: CPython 3.12.13, pytest 9.1.1, PyYAML 6.0.3,
Playwright 1.62.0 with real Chromium, httpx 0.28.1, FastAPI 0.141.1.

| Check | Result |
| --- | --- |
| Final full regression with real Chromium | 4306 passed, no skips, one existing Starlette/httpx deprecation warning; 492.34 s |
| New core action-boundary module | 43 passed |
| Sequential real-browser and Demo suite, including six new Chromium controls | 570 passed, no skips; 454.20 s |
| Fresh dev-only Python 3.11.15 | 3729 passed, one expected optional Demo collection skip; 44.15 s |
| Fresh dev-only Python 3.12.13 | 3729 passed, one expected optional Demo collection skip; 43.12 s |
| Independent core review | 46 boundary/litmus tests and 733 related regression tests passed; three additional runner probes passed |
| Independent consumer/document review | 194 focused tests and 19 additional names-only/mapping probes passed |
| Vocabulary, tracked YAML/YML and include-pin baseline | All 78 files byte-identical to starting main |
| Lock, hygiene, unstaged/cached whitespace checks | Passed; index empty at local acceptance |

Reproduction from the public repository root:

```sh
uv run --frozen pytest tests/test_action_port_boundary.py
uv run --frozen pytest tests/browser tests/demo --tb=short
uv run --frozen pytest -o addopts='' -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Each fresh core environment was created with `uv venv --python 3.11` or `3.12`
in its own temporary directory, then installed using
`uv pip install --python <environment>/bin/python -e '.[dev]'` and ran
`<environment>/bin/python -m pytest -o addopts='' -q`.
Those environments contain no Playwright, httpx, FastAPI or Demo extras.
Their optional collection skip does not substitute for real-browser execution.
The full/core suites include import litmus, executable documentation, declaration
boundaries, and independent Documents/minimal consumer checks.

## Scope and limitations

The accepted R1 documentation revision is preserved and included in this task's
public scope. It changes the composition commitment, not runtime behavior.
No Scenario YAML, include lock, vocabulary, schema version, dependency, CI,
target-application behavior, MANIFESTO or BRAND file changed. No new status,
assertion, value form, mapping language, database probe or Flow feature was added.

Source review covers new files as well as tracked differences, using only neutral
public requirements and synthetic consumers. The repository hygiene script alone
does not certify source neutrality. Historical records remain historical.

This is an explicit Python adapter API break. Private consumers need a separately
authorized migration. The [threat model](../threat-model.md) bounds the result:
reduced accidental expectation coupling and shared-data mutation, not a sandbox,
independent proof of target events, or certification of adversarial adapters.
Opaque handles retain their documented ownership. No universal immutability,
redaction, mapping fidelity, review-cost reduction, or business coverage is claimed.

No unresolved audit findings remain. At local acceptance all task changes are
unstaged and uncommitted, on the starting main. The maintainer's explicit
submission instruction now applies to the accepted scope below; PR/main checks
and branch cleanup must still complete before publication is reported as finished.

Accepted scope (67 files):

```text
SCENARIO.md
adapters/demo/resolver.py
adapters/demo/ui.py
adapters/documents/resolver.py
docs/boundaries.md
docs/browser-support.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/action-port-boundary-acceptance.md
docs/tasks/action-port-boundary.md
docs/threat-model.md
examples/minimal/adapters.py
refracto/ports.py
refracto/projection/backend.py
refracto/projection/ui_stepwise.py
refracto/runner.py
refracto_browser/_support.py
tests/browser/adapter.py
tests/browser/test_action_port_boundary.py
tests/browser/test_anonymous_users.py
tests/browser/test_business_headers.py
tests/browser/test_form_requests.py
tests/browser/test_query_parameters.py
tests/browser/test_response_field_comparison.py
tests/browser/test_response_member_references.py
tests/browser/test_response_numeric_length.py
tests/browser/test_run_values_concat.py
tests/browser/test_support.py
tests/demo/test_demo_backend.py
tests/demo/test_demo_failure_continuation.py
tests/demo/test_demo_include.py
tests/demo/test_demo_stepwise_e2e.py
tests/demo/test_demo_user_contexts.py
tests/fakes.py
tests/named_results_fault_controls.py
tests/test_action_core.py
tests/test_action_port_boundary.py
tests/test_anonymous_users_inclusion.py
tests/test_backend_resolved_bindings.py
tests/test_browser_support_lifecycle.py
tests/test_browser_user_bindings.py
tests/test_business_headers.py
tests/test_collection_matching_count.py
tests/test_contract_execution_boundaries.py
tests/test_e2e_stepwise.py
tests/test_execution_evidence_edges.py
tests/test_failure_continuation.py
tests/test_field_absent.py
tests/test_field_comparison_consumers.py
tests/test_frontend_stepwise.py
tests/test_http_status_assertions.py
tests/test_member_reference_consumers.py
tests/test_numeric_check_consumers.py
tests/test_opensource_litmus.py
tests/test_path_segment_boundaries.py
tests/test_projection_backend.py
tests/test_projection_e2e_contract.py
tests/test_query_parameters.py
tests/test_response_field_comparison.py
tests/test_response_member_references.py
tests/test_response_numeric_length.py
tests/test_run_values_runtime.py
tests/test_runner.py
tests/test_scenario_include.py
tests/test_ui_users_sessions.py
tests/test_users_sessions_core.py
tests/ui_support.py
```
