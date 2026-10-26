# Scoped unique values and explicit literal parameters

Status: expression and implementation authorized on 2026-10-26; independent
audit and architect local acceptance passed on the same date. The maintainer
subsequently authorized public submission separately. Starting main was `85bb13d`
plus the locally accepted run-value diagnostic corrections, which are retained
with their historical results. The dated acceptance below records the state
before submission; hosted checks and delivery are evidenced by the task PR.

## Purpose and sources

Use only public declarations, implementation and synthetic Records/Documents
consumers. No private workspace access. Prevent accidental reuse of generated
identifiers across independent execution scopes, and reject reference-looking
parameter data unless the author explicitly declares it literal. Keep format 1,
the existing Scenario structure and one-level pinned inclusion. Do not change
users, authentication sessions, assertion vocabulary or time representations.

## Approved unique-value semantics

- Each directly declared `{from_run: unique}` parameter is an independent source.
  Repeated references to that source reuse its value; declaring two parameters
  creates two different values. Values remain 32-character UUID4 hex strings.
- Backend, frontend and e2e executions bind independent values. Contract uses
  backend's frozen declaration values and provider recordings; it never generates
  its own values. No guessing whether an HTTP method has side effects.
- Each include instance has its own default sources. Preserve typed parent
  references in explicit `with` arguments rather than copying and regenerating
  their declarations. An explicit caller value remains unchanged, including
  intentionally sharing one value across two includes. Caller concat and actual
  response overrides preserve their normal dependency and type rules.
- Poll attempts and retries of a step reuse its parameter values. Calling the
  runner again generates fresh values. This does not promise absolute collision
  impossibility, target-state isolation, cleanup or successful duplicate writes.
- A time-bearing logical run still samples the UTC clock once. All projections
  and includes share its base and actual/fixed provenance. Fixed time does not
  fix unique values. Prepare all selected executions before any adapter/port call.
- Loading, validation, expansion and impact inspection stay symbolic. No random
  generation or clock reading occurs there or in filtered runs.

## Runtime evidence and low-level binding

Replace the now-misleading single `RunReport.run_unique` value with sensitive,
repr-hidden `run_unique_values`: projection name to compiled parameter name to
actual generated value. Include contract's backend values, with independently
owned metadata dictionaries. Only unique source declarations are recorded;
do not serialize arbitrary parameters or concat business values. The bound
Scenario carries its flat `run_unique_values` mapping with the same protections.

The explicit low-level `bind_run_values` returns `(bound_scenario, unique_values)`
where the second value is this source-value mapping, not a single token. This is
an intentional Python metadata/API change accompanying the approved semantics;
do not maintain an ambiguous compatibility value. Low-level projections still
require explicit binding. Existing time metadata keeps its meaning; compiled
parent aliases are not misreported as independently generated time sources.

Frontend mock responses remain separately authored evidence. Never rewrite a
mock response from expectations or auto-fill it with a newly generated value.
Tests may inject deterministic generation or explicitly bind a declaration before
low-level execution to construct independent fixtures. No new mock factory API.

## Approved parameter expression

```yaml
parameters:
  first_code: {from_run: unique}
  second_code: {from_run: unique}
  code_alias:
    concat: [{from_parameter: first_code}]
  payload:
    literal:
      meta: {from_run: unique}
```

The existing direct whole-parameter `from_run` and `concat` forms remain valid.
Outside those parsed forms, recursively reject dictionary keys beginning with
`from_` and the exact key `concat` anywhere in authored parameter values,
including lists. Reject a direct `from_parameter` mapping instead of sending it
as a literal object. This namespace rule does not inspect parameter names or
ordinary string contents and is not a general typo checker.

Only at a whole parameter value, `{literal: <finite JSON-like data>}` explicitly
preserves the wrapped data. The wrapper must have exactly one key. A whole value
mixing `literal` with other keys is invalid. Inside the wrapper, all keys and
values are data, including further `literal`, `from_run`, `from_parameter` and
`concat` dictionaries. No recursive interpretation. False, zero, empty string,
null, arrays and objects retain their types. Other use-site restrictions remain.
An ordinary nested `literal` key is not an escape for a reserved key beneath it;
the wrapper must surround the complete parameter value.

This check applies to authored parameter declarations only. Never interpret or
reject actual responses or values obtained through a parameter reference because
their keys resemble syntax. Include overrides continue to use existing value
forms; they can reference a literal parameter. No step-level literal expression,
general alias form, expression language, new escape outside parameters or implicit
conversion is added. Expanded review must distinguish data objects from typed
references without revealing runtime values.

## Tests and gates

1. Stateful shared-target backend/e2e executions with and without a uniqueness
   constraint now succeed using distinct values; contract follows backend exactly.
   Keep negative controls: explicit repeated values still produce truthful failures.
2. Repeated include defaults differ; parent-to-child references and concatenations
   share the intended value; independent parameters differ. Cover child-dependent
   defaults, named results, selected response members, order independence,
   filtering, concurrency, no source mutation and one-level rejection.
3. Cover API execution and actual Chromium mock/live observations. Keep independent
   synthetic Documents consumption, and do not infer real-product adoption.
4. Verify one UTC read per logical run across projections, fixed replay, existing
   offset errors before ports, unchanged authentication/session behavior, and
   sensitive metadata hidden from default representations.
5. Reject reserved keys at all authored parameter depths and wrapper misuse.
   Wrapped data must survive binding, includes, review expansion and actual sends
   unchanged. Cover actual response dictionaries containing reserved keys.
6. Explicitly migrate tests that asserted the superseded shared-token or implicit
   literal rules; preserve their negative intent. Historical measurements stay
   historical, with a later transition note rather than rewritten results.
7. Independent audit, full sequential regression with Chromium, fresh core-only
   regression, executable documentation, import litmus, lock, hygiene, diff and
   empty-index checks. Leave all work unstaged, uncommitted and unpushed.

## Exclusions

No Flow, deeper inclusion, token-length selection, additional time formats,
timestamp ordering assertions, automatic reauthentication, preparation-error
report redesign, new assertion checks, environment changes or private adapters.

## Local acceptance, 2026-10-26

The implementation satisfies the approved source, projection and include-instance
rules. Explicit parent references retain their source instead of copying a new
generator into the child. All execution copies bind before ports; contract gets
an independent copy of backend's frozen declaration. One logical UTC base is
still shared. The low-level Python API and sensitive report metadata changed as
specified above; the YAML format version and inclusion depth did not change.

Literal wrapping is checked only while loading authored parameters. Expanded and
impact review show effective data distinctly from references. Returned response
objects are never reinterpreted. Existing tests for implicit literal data and a
single shared token were migrated to the approved rules without removing their
business/evidence checks. Historical acceptance measurements remain historical.

| Check | Observed result |
| --- | --- |
| `uv run pytest -o addopts='' -q` | Exit 0; 4257 passed, no skips, one existing dependency deprecation warning; real Chromium ran sequentially |
| Fresh Python 3.11 environment, editable `.[dev]`, `python -m pytest -o addopts='' -q` | Exit 0; 3686 passed, 1 optional integration collection skip |
| Fresh Python 3.12 environment, editable `.[dev]`, `python -m pytest -o addopts='' -q` | Exit 0; 3686 passed, 1 optional integration collection skip |
| `uv run pytest tests/browser/test_run_values_concat.py -o addopts='' -q` | Exit 0; 13 passed, including actual backend, mock frontend, live e2e and recorded contract in one run |
| `uv run pytest tests/test_opensource_litmus.py -o addopts='' -q` | Exit 0; 3 passed |
| Independent audit | PASS; 463 targeted tests, then 62 final consumer/documentation/CLI/reuse tests; additional independent literal review and probes found no blockers |
| `uv lock --check`, repository hygiene, `git diff --check`, `git diff --cached --check` | Exit 0; index empty |

Audit and targeted-suite counts overlap and must not be added to the full-suite
total. The browser check used separately authored mock fixtures and actual HTTP
recordings; expectations were not used to repair observations. Independent
Records and Documents shared-target controls both pass with distinct generated
values. A repeated explicit parent value still causes a truthful duplicate-write
failure, and ambiguous actual list matches still fail their existing checks.

An intermediate fresh-core run exposed five stale test expectations for the old
implicit-literal, single-token return and inlined include-reference behavior.
Those fixtures/assertions were updated, then the final suites above passed. Two
preparatory long regressions were deliberately interrupted before completion;
neither is reported as acceptance evidence. No implementation findings remain
open in the independent audit.

The assertion vocabulary, ports, session implementation, dependency lock and CI
configuration are byte-identical to starting HEAD. Public source review used only
public code and synthetic examples. No private workspace was accessed. All task
changes remain unstaged and uncommitted on main, whose HEAD and origin/main remain
`85bb13db9e79296cbcf71984231851d4c3574c62`. Local acceptance does not authorize
submission or establish hosted CI results.

Remaining limits are intentional: values are probabilistically unique, not a
target-state isolation or cleanup mechanism; fixed/shared business inputs may
still collide. Additional time formats, token lengths, Flow and preparation-error
report conversion remain outside this task.

## Accepted file scope

This scope includes the preceding locally accepted diagnostic corrections; no
other files are authorized for a later submission by this acceptance.

```text
SCENARIO.md
docs/onboarding.md
docs/roadmap.md
docs/tasks/run-relative-time.md
docs/tasks/run-values-concat.md
docs/tasks/run-value-boundary-review.md
docs/tasks/scoped-unique-values-literal-parameters.md
examples/documents/scenarios/run_unique_create_locate_read.yaml
examples/minimal/run_unique_create_locate_read.yaml
refracto/declaration/impact.py
refracto/declaration/includes.py
refracto/declaration/loader.py
refracto/declaration/model.py
refracto/declaration/run_values.py
refracto/report.py
refracto/runner.py
tests/browser/test_run_values_concat.py
tests/test_authoring_value_boundaries.py
tests/test_concat_dependencies.py
tests/test_include_cli.py
tests/test_literal_parameters.py
tests/test_run_time_consumers.py
tests/test_run_time_declaration.py
tests/test_run_time_documentation.py
tests/test_run_time_inclusion.py
tests/test_run_time_offset_diagnostics.py
tests/test_run_time_runtime.py
tests/test_run_value_consumers.py
tests/test_run_value_scope_boundaries.py
tests/test_run_values_declaration.py
tests/test_run_values_documentation.py
tests/test_run_values_runtime.py
tests/test_scenario_impact.py
tests/test_scenario_include.py
tests/test_scenario_named_results.py
tests/test_scenario_path_reuse.py
tests/test_scoped_unique_binding.py
tests/test_stabilization_documentation.py
```

## Subsequent submission authorization, 2026-10-26

After accepting the completed implementation, the maintainer separately authorized
submission of the accepted public file scope: a dedicated task branch, task
commit, pull request, green checks before merge, successful main checks and branch
cleanup. This includes the preceding accepted diagnostic corrections. No private
workspace operations or new implementation scope are authorized. The submission
preflight independently confirmed the 38-file scope and public information boundary.
