# Named Scenario results: local acceptance

## Decision and scope

Architect acceptance: **PASS**, following independent audit, on 2026-10-15.
This is local implementation acceptance, not submission or release authorization.
No files were staged or committed; no push, PR, merge, or hosted CI was performed.
Private workspaces were neither accessed nor changed.

Authority is the [approved named-results specification](scenario-named-results.md).
The starting tree was the already locally accepted, unsubmitted include change
over main `9bebfa7559bfc22e7121bc31b1945e803676a1f8`, not a clean main checkout.
The [previous acceptance](scenario-include-acceptance.md) remains byte-identical
historical evidence. Its old direct-child syntax is not a compatibility mode.

Delivered: optional multiple `results` aliases, caller `result` references,
strict local/caller scope validation, symbolic review expansion, maintained API
and UI examples, documentation, and negative/runtime tests. Parent references
no longer expose internal child step IDs. Result values come from current-run
normalized responses. No runtime result store or new call/return mechanism.

One-level inclusion, same actor, exact raw-byte sidecar pins, existing actions,
assertions, fail-fast, and sensitive report boundaries remain. Missing/null
consumed results fail before their action; unused outputs do not invent checks.
Children cannot re-export another include's results. No adapter, port, projection
loop, product implementation, MANIFESTO, BRAND, or dependency change was needed
for this slice.

## Verification

Installed environment: Python 3.12.13, pytest 9.1.1, PyYAML 6.0.3,
Playwright 1.62.0. Commands below ran from the public repository.

| Check | Result |
| --- | --- |
| `uv run --locked --no-sync python -B -m pytest -o addopts='' -q` | **1101 passed**, no skips, one existing Starlette/httpx deprecation warning; 124.95 seconds. |
| Separate temporary environment installed with only `.[dev]`, same Python, then `python -B -m pytest -o addopts='' -q` | **987 passed, 1 skipped**; optional Demo collection intentionally unavailable; 34.14 seconds. |
| Core developer: named-results, existing include, and CLI suites | **204 passed**, including 87 new named-results cases and two new CLI cases. |
| Independent auditor: named-results, include, CLI, fault controls, documentation | **228 passed**. |
| Independent auditor: `tests/demo/test_demo_include.py` | **10 passed**, real backend/contract and Chromium frontend/e2e, no skips. |
| Root: litmus and repository hygiene tests | **7 passed**. |
| Root: current named-results fault suite | **20 passed**. |
| All maintained Scenario files under `scenarios/`, minimal and documents examples | **15 loaded successfully**, including exact dependency pins. |
| `refracto validate` for both include parents and explicit expansion tests | Passed; named interfaces and verified symbolic sources visible without execution. |
| `uv lock --check`, repository hygiene script, `git diff --check`, cached diff check | Passed. |

Initial capability tests were run before implementation: two named-results
positive/boundary cases failed and eight rejection cases passed. Separately,
five docs/example checks failed on unsupported `results`; six current-syntax
fault executions failed before running and were not miscounted as detections.
These were red checks, not baseline quality claims. All passed after development.
A preliminary full run collected fewer tests while test writing was in progress;
the final 1101-test run above supersedes it.

The independent auditor also exercised nested later-include arguments, unused
missing outputs, literal result names with punctuation, reference-shaped observed
data, separate-run isolation, repr privacy, and recursive attempts to access
internal child sources. No actionable findings remained. The auditor did not
claim to rerun root's entire installed or isolated-environment suite.

## Behavior demonstrated

- Multiple aliases can select one or several local request-bearing steps.
  Actual runtime values are carried through all existing value positions,
  including a subsequent include's arguments.
- An internal step rename plus an updated child mapping leaves parent YAML
  unchanged. The old pin fails until explicitly updated.
- Wrong/missing/forward result names, mixed reference forms, requestless sources,
  re-exports, qualified internal-source access, nesting, actor changes, and
  invalid pins fail before adapter activity.
- Missing/null consumed fields produce ERROR with no partial binding map.
  Zero, false, and empty strings retain their types. Response equality does not
  collapse booleans into integers.
- A producer success followed by child FAILED/ERROR/SKIPPED still blocks the
  parent consumer. Result declaration is not early return or a new assertion.
- Public Demo verifies multiple observed outputs, fresh repeated invocations,
  shared UI context, and independently authored flat-flow equivalence. The
  approved create/update/read documentation pair also runs on the Demo.
- Default reports do not reveal the sensitive result sentinel. Expansion is
  declaration-only, symbolic, explicit, and still subject to source confidentiality.

## Preserved fault evidence

The current-syntax `tests/named_results_fault_controls.py` independently authors
named-result declarations and reuses the original fault service, normalizer,
authenticator, recorder, and independently authored flat controls. It does not
patch frozen fixture globals or generate expected flows with the expander.

| Fixed backend fault | Current flat | Named-result include | Non-fault neighbor |
| --- | --- | --- | --- |
| Accepted rejection | Detected | Detected | Passed in both forms |
| Changed collection target | Detected | Detected | Passed in both forms |
| Wrong object read | Detected | Detected | Passed in both forms |

All three are valid, reached faults: **3/3** detected, matching historical flat
observations. Setup errors remain invalid controls. This is not a product-quality
percentage or evidence about unmeasured projection fault coverage. The old include
declarations in the frozen harness remain historical, not current runnable syntax;
the current tests use the explicitly separate migrated fixture set.

Frozen file SHA-256 values remain unchanged:

| File | SHA-256 |
| --- | --- |
| `tests/include_fault_controls.py` | `caf1932c715316b95859c2554e5370f1a00d3f11b84a5505cc31e3f800739733` |
| `tests/include_fault_controls_baseline.json` | `3057742b7d89587e1ad5a64c38a2b0a8a757a1539ad76825427f5449bb1c9d36` |
| `tests/include_fault_controls_candidate.json` | `3e448db12df795d66bf5994e5f9b648bc7d5d4085cf05e46a8c80d7e878ec18b` |
| `docs/tasks/scenario-include-acceptance.md` | `cb9020e3f916b7ac3d6ba2296ba162067f98c3c936b4df848e9f1be87b5c852a` |

Accepted implementation anchors:

| File | SHA-256 |
| --- | --- |
| `docs/tasks/scenario-named-results.md` | `02f13dab711f43ff8318c0ed1bd832a924af05cf03162d39b187eeab09fe1e64` |
| `refracto/declaration/model.py` | `0edb10ffdd103359fa764eab5c4605ef499a8f2754182bf64de3ad1f6635ca76` |
| `refracto/declaration/loader.py` | `8d8ca6f1735f55170f74961bae266feccc50adff4560158bd1a8e4d62e40c3c6` |
| `refracto/declaration/expansion.py` | `d895f3bd0fa71d5b6c872cc188b9bf8d292a626541a4441a7bfe34eb327eb7d8` |
| `tests/test_scenario_named_results.py` | `5fbb2c46d68e8f054d27e41009ae3eefee72e2dc1fba4398ff2a86e8c2d9375a` |
| `tests/named_results_fault_controls.py` | `0d8e7239c2f93c0887d11f810e41e61281262c98d863988d8920f273fda9a7dd` |

## Accepted cumulative file scope

The pending public change consists of these **33 files**, including the earlier
accepted include slice. A later submission must use this exact scope and recheck
for unexpected changes. Historical assets listed here are new relative to main,
but were not rewritten by the named-results slice.

```text
SCENARIO.md
docs/roadmap.md
docs/tasks/scenario-include.md
docs/tasks/scenario-include-acceptance.md
docs/tasks/scenario-include-fault-controls.md
docs/tasks/scenario-named-results.md
docs/tasks/scenario-named-results-acceptance.md
refracto/cli.py
refracto/declaration/binding.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/declaration/expansion.py
refracto/declaration/includes.py
refracto/report.py
refracto/runner.py
scenarios/demo_include_items.yaml
scenarios/demo_include_items.includes.json
scenarios/demo_include_items_ui.yaml
scenarios/demo_include_items_ui.includes.json
scenarios/include_shared/create_item.yaml
scenarios/include_shared/create_item_ui.yaml
tests/demo/test_demo_include.py
tests/fixtures/include_demo_flat/items.yaml
tests/fixtures/include_demo_flat/items_ui.yaml
tests/include_fault_controls.py
tests/include_fault_controls_baseline.json
tests/include_fault_controls_candidate.json
tests/named_results_fault_controls.py
tests/test_include_cli.py
tests/test_include_documentation.py
tests/test_include_fault_controls.py
tests/test_scenario_include.py
tests/test_scenario_named_results.py
```

Public information-source review used synthetic requirements, public Demo/code,
and these local engineering checks only. No private product names, adapters,
evidence, paths, or copied private facts are introduced. Hygiene covers tracked
files mechanically; new untracked files were additionally inspected. It is not
a substitute for the information-source review.

## Limits and next gate

The local interpreter was Python 3.12.13. Hosted CI, including its Python 3.11
matrix, remains a separate submission gate. No claim of hosted CI success is made.
Human review-cost savings, approval quality, business coverage, and real-product
adoption remain unmeasured. A pin still proves bytes, not approval. No private
Scenario migration, multi-actor or multilevel inclusion is authorized.

Final state: public HEAD and local origin/main remain the starting commit; the
accepted changes are unstaged and uncommitted. Private workspace state was not
inspected or altered. The task-owned temporary verification environment was
removed after the checks. The next action requires a separate maintainer instruction; do not infer
submission from this acceptance.
