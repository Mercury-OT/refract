# Minimal Refract Onboarding

This guide is anchored in the tested, clean-room example under
[`examples/minimal/`](../examples/minimal/). The target is a neutral in-process
REST application: it needs no network, browser, telemetry, or product-specific
service. Its create endpoint returns bare JSON and its delete endpoint returns an
empty 204 response.

## The minimum integration surface

A request/response-only integration needs four adapter-facing pieces:

1. `Authenticator` binds each logical user to a fixed principal and creates a
   fresh `UserSession` when core requests authentication. Core owns session reuse.
2. `ApiDriver` executes the resolved request against the target.
3. `ResponseNormalizer` maps target responses into Refract's success flag and
   field map.
4. `resolve_request` maps a declared logical request to the target's real request.

The minimal wiring is copied directly from
[`examples/minimal/adapters.py`](../examples/minimal/adapters.py):

```python
def build_adapters(app: MinimalRestApp | None = None) -> runner.Adapters:
    app = app or MinimalRestApp()
    return runner.Adapters(
        auth=MinimalAuthenticator(),
        api=MinimalApiDriver(app),
        state=None,
        ui=None,
        recorder_factory=InMemoryRecorder,
        resolve_request=resolve_request,
        normalizer=MinimalResponseNormalizer(),
    )
```

The recorder is Refract's existing in-memory recorder, not another target port.
The example implements no `StateProbe` and no `UiDriver`.

The declaration uses `schema_version: 1`, a required `users` list, a `parameters` mapping, and ordered
steps. API commands are under `do.request`; response checks are under
`expect.response`. Preparation is another visible step. Later steps can use
`{from_step: create, response_field: id}` without declaring binding aliases.
See [SCENARIO.md](../SCENARIO.md) for the complete contract. Old unversioned and
`version: 2` files and the old `actor` field are rejected, not silently upgraded.
With one participant, ordinary steps may omit `user`; with multiple participants,
every ordinary step names one. Reserved `anonymous` may appear in `users`, so
`users: [creator, anonymous]` supports authenticated and unauthenticated actions
in one flow. `users: []` retains its implicit anonymous behavior. Anonymous
actions never authenticate, inherit another user's credentials, or log that user
out. `session: new` on a named-user leaf replaces only that user's current session,
using the same account, not a fresh role assignment; anonymous renewal is invalid.
See [users and sessions](../SCENARIO.md#users-and-current-sessions).

A one-level include can map each local child participant through `with_users`.
Multi-user children require the complete mapping; single-user children also
retain their existing shorthand. Reusing child bytes does not approve new caller
mappings or change child expectations. See the paired Documents callers for a
[named peer](../examples/documents/scenarios/mapped_peer_access.yaml) and
[anonymous participant](../examples/documents/scenarios/mapped_anonymous_access.yaml).
Their common child explicitly allows 401 or 403; each parent separately checks
its exact refusal. A fixed 403 expectation is never broadened automatically.

Ordinary assertion failures are retained while later steps continue by default.
Put `on_failure: stop` on a leaf step when that failure should stop the remainder.
A step needing an unavailable response value is BLOCKED before its action;
independent later steps may run. Execution errors and explicit skips still stop
the projection. A later successful deletion does not make an earlier failed
check pass, and this is not guaranteed cleanup. The strict gate below remains
unchanged. See [continuation and stopping](../SCENARIO.md#continuing-and-stopping).

The example resolver translates the declaration's `records` path to the target's
`/items` route. Keep this boundary explicit in a real integration: declarations
describe logical requests, while `resolve_request` owns target routing and
mechanical transport mapping. Per-request filtering and pagination belong in an
explicit `query` mapping under `do.request`; resolvers preserve those values
without synthesizing business defaults from global parameters. `RequestSpec.query`
holds decoded wire strings, and the driver encodes them at the transport boundary.
The optional UI `expect.request.query` checks the query actually emitted by the
browser. Omission leaves that check out, while an empty mapping requires no query.
See [query rules](../SCENARIO.md#request-query-parameters) and the complete
[filter and next-page example](../examples/documents/scenarios/filter_and_next_page.yaml).
That example follows an observed cursor in a separate declared request; it needs
a fresh isolated Documents target, not hidden adapter preparation.

Business request headers belong in an optional `headers` mapping, not implicit
resolver inputs. Drivers preserve those values and reject collisions with
session-owned credentials. UI header requirements check actual browser traffic
without supplying the expected values to the page. Response `header_equals` and
`header_absent` use complete raw header observations, not normalized fields or
an empty dictionary standing in for unavailable evidence. Names are
case-insensitive; values are exact strings. See the
[header contract](../SCENARIO.md#business-request-headers) and the complete
[idempotent retry/read declaration](../examples/minimal/idempotent_create.yaml).
The latter is a separate header-capable example; the introductory minimal
driver below is not silently upgraded into a complete header recorder.

`ResponseNormalizer` owns response-shape differences. A target may return a
product envelope, bare JSON, or an empty 204 response; the adapter must convert
all of those into a truthful `NormalizedResponse`. In this example, bare JSON
becomes the normalized field map, while 204 becomes `succeeded=True` with
`fields={}`.

## Projection capabilities

Run `contract` together with `backend`. Contract consumes the recordings made by
the backend projection and is rejected if requested on its own. The tested
[`create_and_delete.yaml`](../examples/minimal/scenarios/create_and_delete.yaml)
scenario uses only declared requests and response assertions, then runs with
`("backend", "contract")`.
Contract checks response compatibility over the verified backend recordings.
It neither sends the query again nor independently observes the query on the wire.

`StateProbe` is optional until a scenario declares `backend_state` assertions.
Without it, those assertions are skipped as an explicit degradation. The report
keeps `status == "DEGRADED"`, and `rep.degradations()` exposes the projection,
step id, and reason. The
[`state_degraded.yaml`](../examples/minimal/scenarios/state_degraded.yaml) scenario
is the CI anchor for this behavior.

UI primitives need a stepwise UI adapter. Unsupported projection/action
combinations are rejected before target side effects. Frontend does not execute
direct API steps. E2e may execute explicitly declared API steps without a
browser; it must never send an extra request to repair missing or incorrect UI
traffic. Selecting backend does not verify UI interactions.

## Strict quality gates

Do not use `assert rep.passed` as a strict gate: `passed` deliberately includes
`DEGRADED`. The only strict gate is `rep.status == "PASSED"`. An empty
`rep.degradations()` is a useful supplementary observation, but it must not be
used as a gate on its own: `EMPTY` and `NOT_SELECTED` reports also have no
degradations. This runnable check is copied directly from
[`examples/minimal/run_example.py`](../examples/minimal/run_example.py):

```python
def run():
    adapters = build_adapters()
    rep = runner.run_scenario(
        SCENARIO_PATH,
        adapters,
        projections=("backend", "contract"),
    )
    # Do not gate on rep.passed: it includes DEGRADED.
    assert rep.status == "PASSED"
    assert rep.degradations() == []
    return rep
```

In that example, the status assertion is the gate. The degradation assertion is
an additional confirmation that no skipped capability is hidden in the report.

## Honest boundary

A request/response-only integration provides request execution, response
assertions, and contract comparison. It does **not** provide internal-state verification
and must not be presented as equivalent to full verification. Add a `StateProbe` when
internal-state evidence is required. Add a `UiDriver` only when frontend or end-to-end
behavior is in scope.

## CI anchors

Every capability claim above is exercised by
[`tests/test_minimal_onboarding.py`](../tests/test_minimal_onboarding.py):

| Claim | Tested source |
| --- | --- |
| Three ports plus `resolve_request` run backend and contract successfully | `run_example.py` and `create_and_delete.yaml` |
| Missing state capability is visible as a degradation | `state_degraded.yaml` |
| Missing UI capability is rejected before side effects | `adapters.py` with `ui=None` |
| Empty 204 responses normalize to success with no fields | `app.py`, `adapters.py`, and `create_and_delete.yaml` |
| Guide code cannot drift away from the example | every fenced block is checked against `examples/minimal/` |
