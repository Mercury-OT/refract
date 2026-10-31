# Object-specific UI selection: acceptance record

Date: 2026-10-31. Starting main: `19d5ef1`. Governing
[specification](ui-object-target-selection.md). Independent audits and architect
acceptance passed. Hosted delivery is separately evidenced by the task PR and
post-merge main CI; a local test pass alone is not hosted delivery.

## Maintainer summary

- A click can select the control belonging to an observed object_id.
- The logical control name remains separate from the object's actual identity.
- Missing, ambiguous or changed identities cannot silently select another row.
- A correct selection cannot excuse an actual request for the wrong object.
- Two new synthetic editors pass the same live six-step Scenario; no existing
  target was changed to make this work. This is not evidence of adoption savings.

## Implemented and reviewed scope

The loader, references, one-level includes, expansion and impact view preserve
the optional click identity. Known bad declarations fail loading; unusable
response-derived IDs block before action. The vocabulary, schema version,
ordinary action semantics and include depth remain unchanged.

Drivers explicitly opt into object selection. A signed permit carries the
selection input without expectations. Core validates an actual-selection receipt
and copies it before other adapter callbacks. Missing receipt, ambiguous counts,
bool/int confusion, mismatched identity and mutation/skip bypasses are errors.
Default repr omits sensitive selection payloads. Backend and contract explicitly
leave UI selection unchecked.

BrowserSupport performs one click on pinned elements and rechecks observed row
identity/control uniqueness at trusted dispatch. Its reader receives only the
actual row, including no requested ID through an implicit JavaScript receiver.
Rows with missing identity are not silently discarded. Existing request,
credential, replay, native-await and mock/live boundaries remain active.

## Actual consumers and controls

The new [example](../../examples/ui_object_targets/README.md) uses one shared HTTP
service and two independently rendered synthetic UIs: table/detail-link and
card/form-action. The normal targets were frozen before adapter/test authoring;
their [source hashes](../../examples/ui_object_targets/target-sources.json) remain
unchanged. Existing target sources and executable YAML were not modified.

Both run API create -> open list -> select that record's editor -> fill -> save ->
API read. The created object is initially not first. Actual captured GET/PATCH
paths and final target state agree on that ID; the other two records remain
unchanged. Reordering rows also passes.

Separate fault subclasses remove/duplicate rows, omit identity, misroute editing
or misroute saving. Tests confirm injection actually occurred. Missing/ambiguous
selection sends no edit request. Wrong-object traffic produces ERROR/BLOCKED;
the wrong-save control explicitly retains the real wrong-object side effect,
which the framework detects but does not undo. A green HTTP read is not separate
database evidence.

## Independent audit

Separate core and browser reviewers did not author the implementation. The core
review passed two reproducible groups: 416 and 355 tests (771 total), covering
declaration/inclusion, ports, execution, reporting, review and documentation.
It also ran 17 exploratory adversarial probes; these were inline checks, not a
retained public benchmark or new coverage percentage.

The browser reviewer independently checked dispatch/identity and consumer source
boundaries. Six additional real-browser probes passed: hidden duplicate scope,
disabled control, unreadable unrelated row identity, pointerdown identity change,
and nested synthetic clicks in both transport modes. Synthetic traffic remained
diagnostic while only the actual trusted target supplied action evidence.

Developer self-review caught and closed two bypasses before acceptance: changing
a scoped permit into an unscoped skip, and a JavaScript reader receiving the
requested identity through its implicit receiver. Permanent regression tests
cover both. Documentation inventory was extended rather than weakening its
exhaustiveness. An offline helper call retained its optional default argument.

## Verification commands and results

All commands run from the public repository. Focused and full runs are separate
observations, not additive totals of distinct checks.

| Command or check | Result |
| --- | --- |
| `uv run --locked --no-sync refracto validate examples/ui_object_targets/scenario.yaml` | Exit 0; six steps, four declared requests, one UI check, twelve response checks. |
| `uv run --extra browser python -m examples.ui_object_targets.run` | Exit 0; both live e2e consumers PASSED with no degradation. |
| Consumer tests | 16 passed, including normal runs and genuine injected faults. |
| Core development regression | 669 passed, including 105 new selection cases. |
| Related browser development regression | 176 passed; additional targeted receiver/navigation/scope checks passed. |
| Python 3.11, dev-only environment: `python -m pytest -o addopts='' -q` | 4241 passed; one optional Demo collection skip because httpx is absent. A local temporary-directory cleanup warning was not a test failure. |
| Python 3.12, dev-only environment: `python -m pytest -o addopts='' -q` | 4241 passed; the same optional Demo collection skip. |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q` | 5032 passed, no skips, one existing third-party deprecation warning; exit 0 in 663.76 seconds. Real Chromium was exercised. |
| `uv lock --check`, repository hygiene, `git diff --check` | Passed locally; staged hygiene is repeated at submission. |

The final negative consumer checks also passed all six cases after using the
normal action-readiness budget, avoiding a short budget for unrelated navigation
and HTTP setup. The generic no-identity-attribute frozen-source check passed.

Independent core command groups:

```sh
uv run pytest -o addopts='' -q tests/test_ui_object_target_core.py tests/test_action_port_boundary.py tests/test_scenario_review_exercise.py tests/test_scenario_impact.py tests/test_include_cli.py tests/test_include_documentation.py tests/test_scenario_include.py tests/test_opensource_litmus.py
uv run pytest -o addopts='' -q tests/test_scenario_named_results.py tests/test_frontend_stepwise.py tests/test_e2e_stepwise.py tests/test_failure_continuation.py tests/test_stabilization_documentation.py
```

The pre-task snapshot covers 88 existing files: executable YAML, browser target
HTML/JavaScript, example app sources, vocabulary, dependencies, CI, principles
and brand files. Their bytes remain unchanged. Public source review used only
existing public implementation and newly authored neutral examples; no private
product, internal name, path or evidence supplied a public fact.

## Limits and delivery gate

Only click has object_id; no dynamic logical target, search, pagination, extra
business action, UI assertion, state-absence check or deeper include was added.
The helper supports safe JavaScript numeric IDs and exact nonempty strings.
The current-document receipt does not survive full-document navigation; that
case fails visibly and has a negative control. Earlier pointer/hover effects
cannot be undone. Mapping truth is not independently certified, and arbitrary
same-process adapters/pages are not sandboxed. Real-product integration remains
separate evidence.

Submission is explicitly authorized by the maintainer after final acceptance.
PR checks, main CI and cleanup remain required; no failing check may be bypassed.
The architect accepted the 38-file implementation, test, synthetic-example and
documentation scope. Vocabulary, dependency/CI files and all existing target
sources remain outside that scope.
