# Scenario include: local acceptance record

## Result and scope

Local implementation, independent audit, and architect acceptance passed on
2026-10-14 against public base `9bebfa7559bfc22e7121bc31b1945e803676a1f8`.
This is not submission or release authorization. Changes remain unstaged and
uncommitted; no branch, push, PR, hosted CI, or private-workspace change was made.

The [approved specification](scenario-include.md) is implemented with identical
parent/child actors and parent `.includes.json` sidecars. A child is verified,
validated independently, and expanded into the existing ordered execution model.
The same existing projection loops, adapter ports, authentication lifecycle, and
contract implementation execute the leaves. No adapter source changes are needed.

The new capability is reusable declared work, not automatic approval or cached
success. Unchanged child internals can reuse their review, but the parent's
purpose, argument values, order, response references, and uncovered obligations
still require review. Parameters can change expected values. Pins prove exact byte
agreement, not human authorization. Review-cost savings remain unmeasured.

## Independent review and corrections

A separate audit agent reviewed the specification, implementation, examples,
tests, and public information boundary without modifying files. It independently
ran 137 focused checks, nine real Demo/Chromium checks without skips, and seven
isolation/hygiene checks. Final audit: PASS; no unresolved blockers.

The review found and closed a real use-site validation gap: a runtime response
could supply a dictionary where a scalar expectation was required, a list as a
whole request body, or an empty path segment. The initial implementation could
send the consuming request and pass. The corrected preparation validates resolved
values before the consuming mapper/action. Independent probes now produce
`PASSED -> ERROR -> BLOCKED`, with only the first request sent. Valid falsy values
and mapping bodies have passing controls. This enforces existing declaration
constraints; it adds no authoring syntax.

The audit also closed malformed dependency-path error handling and added explicit
missing-file, malformed-sidecar, alias, namespace, and expanded-UI preflight
controls. A final comment-only correction updates the binding module's old error
description; the frozen fault harness was rerun afterward against final source
hashes. No executable behavior changed after the final full regression.

## Commands and observations

Commands below ran from the relevant public checkout unless stated otherwise.
`CORE_PYTHON` names the isolated dev-only environment's interpreter; `TARGET`
names a disposable detached verification checkout, and `HARNESS` names the frozen
public fault-control script. These are invocation placeholders, not test data.

| Check | Actual command | Exit / observation |
| --- | --- | --- |
| Baseline regression | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q` in detached baseline, with verified baseline import origin | 0; 863 tests passed, one existing dependency warning. Collection separately confirmed the count. |
| Final full regression | `PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync python -B -m pytest -q -o addopts=''` | 0; 1009 passed, one existing Starlette/httpx deprecation warning, no skips. |
| Final isolated core suite | `PYTHONDONTWRITEBYTECODE=1 "$CORE_PYTHON" -B -m pytest -q -o addopts=''` in detached candidate | 0; 896 passed, one optional Demo collection skipped. |
| Include-focused audit | `uv run --locked --no-sync python -B -m pytest tests/test_scenario_include.py tests/test_include_cli.py tests/test_include_documentation.py tests/test_include_fault_controls.py -q -o addopts=''` | 0; 137 passed. |
| Real browser/API consumers | `uv run --locked --no-sync python -B -m pytest tests/demo/test_demo_include.py -q -o addopts=''` | 0; nine passed, no skips. |
| Import direction and hygiene tests | `uv run --locked --no-sync python -B -m pytest tests/test_opensource_litmus.py tests/test_repository_hygiene.py -q -o addopts=''` | 0; seven passed. |
| Dependency lock | `uv lock --check` | 0; lock unchanged. |
| Repository scan | `bash scripts/check_repository_hygiene.sh` | 0. Untracked additions were separately inspected, not silently treated as scanned tracked files. |
| Whitespace and index | `git diff --check`; `git diff --cached --check` | Both 0; index empty. |
| Maintained declarations | `uv run --locked --no-sync refracto validate <file>` for all YAML under `scenarios/`, `examples/minimal/scenarios/`, and `examples/documents/scenarios/` | All 15 passed, including real include sidecars. |

Both local environments use Python 3.12.13. The isolated environment was installed
with only the existing `[dev]` extra and imports the detached candidate. It has
neither Playwright nor FastAPI. Hosted CI, including its Python 3.11 matrix entry,
has not been run; it remains part of a separately authorized submission.

Before implementation, nine of the initial 24 include/CLI checks failed because
the feature was absent. Five initial include Demo checks failed while the three
independently handwritten flat controls passed. The baseline fault pytest run
had ten passing checks and eight include-feature failures. These are red-feature
observations, not fault detections. Later boundary cases were added during
development/audit; not every new test is claimed to have been run against baseline.

## Execution equivalence and fixed fault controls

The public API example compares included and independently handwritten flat flows
using backend plus contract. The UI example executes real Chromium in both mock
frontend and live e2e modes. It checks one context/session per projection, eight
explicit actions, ordered repeated-endpoint mocks, actual response handoff,
qualified step ownership, and failure blocking the later inclusion. The API and UI
examples use the same child twice with separate values and results.

Three fixed backend faults were frozen before core changes, with the same
assertions, observation sources, passing neighbors, and reachability checks:

| Fault | Baseline flat | Final candidate flat | Final candidate include |
| --- | --- | --- | --- |
| Incorrect success for declared rejection | Detected | Detected | Detected |
| Changed target in a collection | Detected | Detected | Detected |
| Wrong object returned after response-based lookup | Detected | Detected | Detected |

Each column has three valid executed faults, all detected, with three passing
neighbors and no exclusions. All 12 candidate observations match their baseline
counterparts after only the frozen form/step-prefix normalization. There is no
claimed gain in detection strength, general mutation score, or product quality.

Execution from outside the source checkout:

```sh
PYTHONPATH="$TARGET" "$PYTHON" -c 'import refracto; print(refracto.__file__)'
PYTHONPATH="$TARGET" "$PYTHON" "$HARNESS" --flat-only
PYTHONPATH="$TARGET" "$PYTHON" "$HARNESS"
```

Import origin was checked. Candidate commands exit 0. Baseline flat-only exits 0;
baseline with include exits 1 before requests because the feature is absent,
which is not counted as detection. Full observations and final source hashes are
in `tests/include_fault_controls_baseline.json` and
`tests/include_fault_controls_candidate.json` (verification revision 3).

The executable harness SHA-256 remains
`caf1932c715316b95859c2554e5370f1a00d3f11b84a5505cc31e3f800739733`.
The fault definitions and harness did not change after freezing. The companion
fault-control document subsequently gained a baseline-execution record; that
appendix changed its whole-file hash, not the frozen faults or expected outcomes.
The delivery does not claim its original whole-file hash remained unchanged.
Disposable verification checkouts and environments are removed after verification;
the public observations are retained.

## Accepted file scope

```text
SCENARIO.md
docs/roadmap.md
docs/tasks/scenario-include.md
docs/tasks/scenario-include-fault-controls.md
docs/tasks/scenario-include-acceptance.md
refracto/cli.py
refracto/declaration/binding.py
refracto/declaration/expansion.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
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
tests/test_include_cli.py
tests/test_include_documentation.py
tests/test_include_fault_controls.py
tests/test_scenario_include.py
```

## Limits and rejected extensions

- One level, static local targets, identical actors only. No recursion, arbitrary
  expressions, conditions, repeat construct, actor switching, partial inclusion,
  assertion override, exports/returns, or automatic pin update.
- At most 64 distinct children and 1000 expanded leaf steps per composition.
  These are engineering bounds, not measured scale or performance claims.
- Child request-bearing step IDs form a caller-visible interface. Renaming them
  can break callers; no compatibility indirection is promised.
- Explicit `--expand` is a symbolic review view, not executable source or a new
  authoring format. It can disclose declaration literals; normal validation and
  default report representations do not automatically dump call values.
- No graphical workbench, private consumer migration, or approval platform was
  implemented. No private workspace was read or changed.
- No claim is made that a hash proves approval, all parent business obligations
  are covered, real-product adoption is validated, or reviewer effort is reduced.

Public sources are the existing repository, approved neutral requirements, and
synthetic examples. Mechanical hygiene supplements, rather than replaces, the
independent information-source review. No private path, product, organization,
adapter, or local product evidence was copied into this delivery.
