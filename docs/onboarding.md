# Minimal Refract Onboarding

This guide is anchored in the tested, clean-room example under
[`examples/minimal/`](../examples/minimal/). The target is a neutral in-process
REST application: it needs no network, browser, telemetry, or product-specific
service. Its create endpoint returns bare JSON and its delete endpoint returns an
empty 204 response.

## The minimum integration surface

A request/response-only integration needs four adapter-facing pieces:

1. `Authenticator` creates the session associated with the scenario actor.
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

The example resolver translates the declaration's `records` path to the target's
`/items` route. Keep this boundary explicit in a real integration: declarations
describe logical requests, while `resolve_request` owns target routing, headers,
and other transport details.

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

`StateProbe` is optional until a scenario declares `backend_state` assertions.
Without it, those assertions are skipped as an explicit degradation. The report
keeps `status == "DEGRADED"`, and `rep.degradations()` exposes the projection,
step id, and reason. The
[`state_degraded.yaml`](../examples/minimal/scenarios/state_degraded.yaml) scenario
is the CI anchor for this behavior.

`UiDriver` is optional until `frontend` or `e2e` is requested. Requesting either
projection without a UI driver raises a `ValueError` containing `UiDriver` before
any target request is sent. It does not leak an internal attribute error or run
part of the scenario first.

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
