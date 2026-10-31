# Selected compatibility notes

Recorded on 2026-10-31 from public commit history. This is a selected migration
record, not a complete project changelog or a newly published package release.
The development package version remains `0.1.0`; use the commit anchors below
when identifying these Python interface changes.

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
