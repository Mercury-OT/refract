# Collection, action-boundary and migration follow-up

Status: verified against public main `4a4b8af` on 2026-10-31. The maintainer
authorized verification and repair of confirmed findings, followed by independent
audit and architect acceptance. At that stage, submission was not authorized
and all changes remained unstaged. Sources are public implementation/history and neutral reproductions;
no private workspace or product material is an input.
Development, independent audit and local architect acceptance subsequently passed
on the same date; the results below do not authorize submission.

## Findings and scope

| Finding | Verified interpretation | Authorized repair |
| --- | --- | --- |
| Collection hook returns False | It ends pytest's first-result hook before built-in ignore handling; both directory and glob ignores retain browser cases. | Return None when this repository has no reason to exclude a path; retain True for unavailable optional dependencies. |
| No object-absence assertion | Real expression gap, not an incorrect equality result. Complete no-object observations correctly fail equality; unavailable observations are not absence. | Record the gap only; no vocabulary or YAML change. |
| Action callback exception loses its type | Resolver/UI failures retain only the operation label. | Add a safe, fixed built-in exception category without message, repr, module, args or custom class name. |
| Resolver result checked before copying | A custom container's copy can alter the outgoing business body after it passed validation. | Check the raw outer return type, copy once into owned data, then validate that snapshot before executing it. |
| Type-mismatch regression waits thirty seconds | The state-observation timeout, not PollConfig, causes a real thirty-second wait. | Inject the existing fake monotonic clock and sleep, retaining FAILED/type-mismatch and timeout coverage. |
| No consolidated Python migration record | Current migration instructions exist but are scattered; the development package still reports 0.1.0. | Add a dated, commit-linked CHANGELOG entry and discoverable links, not a new release or compatibility shim. |
| Commit bodies omit reasons | Recent public commits use subjects only; task documents contain the detail. | Require a short reason/boundary/validation/task-reference body for future task submissions; do not rewrite published history. |

Preserve format 1, one-level includes, all Scenario bytes, assertion semantics,
port signatures, continuation, authentication and evidence requirements. Do not
add object_absent, rename object_field_equals, change package versions, expand
browser support, or start Flow or storage work.

## Action error and ownership contract

Keep the existing ValueError wrapping and execution ERROR/continuation rules.
Error detail is `<operation> failed (<safe built-in exception category>)`.
Use fixed category strings selected from built-in exception classes; custom
exceptions use an approved built-in base or `Exception`. An arbitrary class name
can contain sensitive data, so it is not copied into the report. Do not evaluate
the exception's str/repr or expose its message, args, module or chained cause.
Do not catch SystemExit or KeyboardInterrupt. This is diagnostic improvement,
not general redaction, arbitrary exception serialization or adapter certification.

Require the resolver's raw return type to be exactly RequestSpec before copying;
a wrong-type object must not become valid through its copy hook. Validate the
owned copy using the existing request ownership checks, including its exact
outer type. Keep retained-alias protection and the unchanged declaration as the
comparison baseline. No additional deep copy is required. This addresses an
unvalidated snapshot under the cooperative adapter threat model; it does not
sandbox malicious in-process objects or arbitrary stateful copy hooks.

Independent review also reproduced a related false-value collapse in this same
comparison: `[]`, false, zero and an empty string must not become an empty body
through `or {}`. Normalize only None to the existing empty-map representation;
preserve strict value/type comparison for everything else. Keep the existing
None/empty-dictionary compatibility. This rejects malformed adapter output and
does not add a declared request-body format.

## Mechanical acceptance

1. Exercise pytest itself in an isolated small project using this repository's
   actual collection hook. With optional dependencies present, default collection
   includes ordinary/browser cases; directory and glob ignores exclude the
   selected browser cases without hiding ordinary tests. Existing absent-dependency
   and similarly named checkout-path controls remain valid.
2. Rerun actual repository collection with each ignore option and check no
   `tests/browser/` node IDs remain. This tests exclusion, not successful browser
   execution. It does not exclude separately located Demo browser tests.
3. Resolver and UI open/action exceptions expose useful safe categories, retain
   ERROR/blocked behavior, omit sensitive message and custom-name sentinels, and
   do not introduce a legacy-signature retry. Preserve real browser regressions.
4. Copy-altered resolver bodies/methods and wrong raw/copied return types produce
   ERROR before ApiDriver.send in backend and explicit-API e2e. Valid requests,
   existing retained-alias/poll tests and input ownership controls still pass.
   Include falsy non-mapping bodies both directly returned and produced by a copy
   hook; None and empty dictionaries remain positive controls.
5. The span type-mismatch test uses zero real sleeping, reaches its original
   observation deadline via the fake clock, and still reports FAILED rather than
   ERROR with the original comparison diagnostic. Record before/after timing as
   a test-cost observation, not a framework performance benchmark.
6. Migration notes match public commit history and current signatures. Distinguish
   low-level bind_run_values callers from adapter protocols. Do not claim the
   selected record is a complete changelog or invent a package release.
7. Run focused controls, dev-only core checks, the complete suite with actual
   Chromium, existing litmus/documentation guards, lock and hygiene/diff checks.
   Confirm vocabulary, YAML, dependencies and CI remain unchanged. Independent
   audit must challenge the fixes before final acceptance.

## Deferred absence proposal

A future exact-ID object_absent check would need a complete zero-match observation;
incomplete, ambiguous, unavailable or malformed evidence must not pass. Known-ID
deletion is a fitting example. A denied create that supplies no ID requires an
additional reviewed selection/evidence plan; exact-ID absence alone cannot prove
that no object was created. Any new expression returns to maintainer review.

## Acceptance

Independent audit passed on the final owned-request implementation. The first
audit found the additional falsy-body collapse described above; it was fixed and
independently retested rather than waived. An earlier full run was interrupted
after that finding and is not final acceptance evidence.

- New real-pytest exclusion controls first produced two failures, then passed.
  Both actual repository ignore commands now collect 4230 tests and zero
  `tests/browser/` cases, rather than retaining the original 612 browser cases.
- The exact state-mismatch test took 30.13 seconds in its original call and
  0.05 seconds total with the fake clock. It still advances thirty simulated
  seconds. Independent verification forbade real time.sleep and still passed.
- The original action-boundary controls produced 26 failures before repair.
  Additional falsy-body controls produced sixteen failures and eight valid
  positive results before that repair. The final related API/e2e/browser panel
  passed 591 tests; the independent focused run passed 103.
- Final isolated dev-only Python 3.11 and 3.12 runs each passed 4133 tests with
  one optional-dependency skip, in 10.22 and 9.87 seconds respectively.
- Existing litmus, Scenario/include documentation and boundary sentinels passed
  101 tests. Lock, hygiene and diff checks passed. New public documents were also
  manually reviewed for neutral sources and local-path/private-data exclusion.
- Final complete regression passed 4842 tests, with actual Chromium and one
  existing third-party warning, in 607.81 seconds. Architect acceptance passed
  for the ten-file repair scope. No unresolved finding remains in that scope.
  At acceptance, submission was not yet authorized and the index was empty.

Reproduction commands from the public repository:

```sh
uv run --frozen pytest --collect-only -o addopts='' -q --ignore=tests/browser
uv run --frozen pytest --collect-only -o addopts='' -q '--ignore-glob=tests/browser/*'
uv run --frozen pytest -o addopts='' -q tests/test_action_port_boundary.py tests/test_browser_collection_gate.py tests/test_projection_backend.py::test_span_attr_type_mismatch_is_failed_not_error
uv run --frozen pytest
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

The timings describe these checks only. The change does not shorten production
polling or state-observation budgets, measure framework throughput, certify
adapters, or implement an absence assertion. Migration notes cover selected
public commits, not an invented release. Published commit history is unchanged.

## Subsequent submission authorization

After reviewing the accepted scope, the maintainer separately authorized staging,
commit, task-branch push, PR creation, merge after green PR checks, verification
of main CI, and branch cleanup on 2026-10-31. This authorizes the ten accepted
repair files only. CI, merge and cleanup outcomes remain subject to actual
verification; this record does not claim they have already completed.

The staged-file hygiene check caught two external commit hyperlinks in the new
changelog. They were replaced with full commit IDs and local git-show guidance,
without weakening the host allow-list or changing implementation files.
