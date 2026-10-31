# Selected compatibility notes

Recorded on 2026-10-31 from public commit history. This is a selected migration
record, not a complete project changelog or a newly published package release.
The development package version remains `0.1.0`; use the commit anchors below
when identifying these Python interface changes.

## 2026-10-31: bounded same-tab object navigation

BrowserSupport can retain an actual scoped-click selection across a supported
same-origin HTML document replacement. Existing ObjectTarget mappings and the
perform_step signature are unchanged. No Scenario migration or schema-version
change is required. A native anchor must itself be the mapped control; a trusted
click handler may also navigate synchronously. Deferred navigation, redirects and
forms are not added. New-document startup requests remain background, and the
destination still needs its declared UI checks. See the
[browser guide](docs/browser-support.md#object-specific-clicks) and
[task contract](docs/tasks/same-tab-object-navigation.md).

## 2026-10-31: object-specific UI click selection

See the [scoped task](docs/tasks/ui-object-target-selection.md) for authorization
and delivery gates. This addition keeps schema_version: 1 and the existing
perform_step signature; ordinary clicks retain their previous mapping.

- A click may now carry object_id. Step and UiActionPermit hide it from default
  repr; it participates in permit signing and strict integrity checks.
- StepwiseUiDriver.supports_object_targeting(mode) defaults to false. Drivers
  supporting scoped clicks must opt in explicitly. Unsupported Scenarios fail
  before UI context creation instead of silently ignoring the ID.
- Scoped UiActionEvidence must contain UiObjectSelection with the actual ID and
  exact integer object_matches/control_matches, both 1. Core checks and copies
  this into StepResult.object_selection. Unscoped evidence must omit it.
- BrowserSupport.perform accepts ObjectTarget as an alternative to url/selector.
  Map existing product identity using rows, relative control and read_id; do not
  inject identity metadata or guess from labels/order. The helper supplies the
  selection receipt and protects selection at click dispatch.

See [the mapping guide](docs/browser-support.md#object-specific-clicks) and
[synthetic consumers](examples/ui_object_targets/README.md). A custom adapter's
receipt is a checked claim, not independent proof of its truthfulness.

## 2026-10-27: operation-only adapter inputs

Commit: `ee4691e0daf04826050b4ea06e94159cee787557` (inspect with `git show <commit>`).

Request resolvers and UI operations no longer receive Scenario, Step or
expectation objects. This reduces accidental dependence on assertions and
mutation of shared declaration data; it does not sandbox adapter code.

| Interface | Before this commit | Current form |
| --- | --- | --- |
| Request resolver | `resolve_request(scenario, step, request)` | `resolve_request(action: RequestAction) -> RequestSpec` |
| UI context creation | `open_stepwise(scenario, session, *, mode, mock_plan=None, mock_queue=None, user=None, session_generation=0, context_id="")` | `open_stepwise(session, *, mode, mock_plan=None, mock_queue=None, user=None, session_generation=0, context_id="")` |
| UI primitive | `perform_step(scenario, step, context, permit)` | `perform_step(context, permit, *, business_header_names=())` |
| UI permit | Included `resolved_bindings` | That field is removed; core retains the binding map. |

For bound methods, the usual `self` parameter is unchanged and omitted above.
To migrate an adapter:

1. Read the resolver's prepared `method`, `path`, `body`, `query` and `headers`
   from `RequestAction`. Preserve the declared business values. Its outer object
   is frozen and its nested data belongs to that invocation.
2. Open UI contexts using the session and explicit lifecycle arguments. Perform
   the primitive described by `permit.action`, `permit.target` and `permit.value`;
   do not recover Scenario or Step access through another route.
3. Accept the immutable, sorted, lowercase `business_header_names` tuple for
   credential-header collision checks. These are names only, not expected
   header values or instructions to inject headers into browser traffic.
4. Remove reads of `permit.resolved_bindings`. Session/context identities and the
   explicit mock queue retain their existing ownership and lifecycle rules.

There is no legacy-signature retry. An incompatible operation remains a visible
execution error rather than receiving the old declaration arguments. Context
close and snapshot signatures are unchanged. This commit did not change Scenario
YAML, include pins or execution states.

See the [current onboarding contract](docs/onboarding.md#the-minimum-integration-surface),
[browser adapter example](docs/browser-support.md),
[approved specification](docs/tasks/action-port-boundary.md) and
[signature/ownership regression tests](tests/test_action_port_boundary.py).

## 2026-10-26: scoped generated values and binding-helper return

Commit: `bb9c680ac68a4b3fb7fe5ce422807174edce569a` (inspect with `git show <commit>`).

This affects direct callers of
`refracto.declaration.run_values.bind_run_values`, a low-level declaration helper,
not an adapter protocol. Its arguments remain `bind_run_values(scenario, *,
run_time=None)`, but the return changed:

- Before: `(bound_scenario, token_or_none)`, with one generated token.
- Current: `(bound_scenario, unique_values)`, where `unique_values` is a copied,
  flat mapping from compiled source-parameter names to their generated strings;
  it is empty when no unique source was generated.

Keep the second result as a mapping; do not treat it as a string or arbitrarily
select its first value. Each independent source parameter generates its own
value; references to the same source reuse that value. Repeated includes have
separate default sources, while explicit parent references intentionally share.
Retain the original symbolic Scenario for a fresh execution: binding an already
bound Scenario is rejected. Direct projection callers must use the prepared
Scenario; contract must reuse the backend's frozen declaration and recordings.

Ordinary `run_scenario` callers do not call this helper themselves. The runner
prepares separate values for executable projections and lets contract reuse the
backend values, avoiding accidental collisions between independent writers.
This selected Python note does not replace the same commit's
[parameter literal and generation rules](SCENARIO.md#parameters-and-prior-response-values).

See the [scoping specification](docs/tasks/scoped-unique-values-literal-parameters.md)
and [binding regression tests](tests/test_scoped_unique_binding.py).
