# Action-oriented Scenario format

Priority and delivery state are maintained in the [roadmap](../roadmap.md).
This task captures the approved expression, execution decisions, and acceptance
scope. The executable reference is [SCENARIO.md](../../SCENARIO.md); delivery
state remains in the roadmap, not in duplicated status summaries.

## Purpose and source

Make a Scenario readable as metadata, parameters, and ordered actions with
expectations. Business preparation and user interactions must be visible in the
declaration rather than hidden in an adapter workflow.

This design uses explicitly approved product-neutral requirements and the
public implementation as its sources. The example below is a synthetic English
rendering of the approved shape, not a byte-for-byte approval artifact. It does
not import any product-specific scenario, behavior, or experiment result.

## Approved expression

```yaml
# Format version is distinct from content revision or approval identity.
schema_version: 1
scenario: records.create
description: Create a record and check its request, response, and page result.
actor: editor

# Declared data, not executable generators or hidden adapter defaults.
parameters:
  record_name: Example record

steps:
  - id: open_list
    do: open
    target: records.page

  - id: open_create_form
    do: click
    target: records.new_button

  - id: fill_name
    do: fill
    target: records.name_input
    value: {from_parameter: record_name}

  - id: submit
    do: click
    target: records.submit_button
    expect:
      # frontend/e2e check the actual request caused by this action.
      # An explicitly selected backend projection sends this declaration.
      request:
        method: POST
        path: [records]
        body:
          name: {from_parameter: record_name}
      response:
        - check: success
        - check: has
          field: id
        - check: field_equals
          field: name
          value: {from_parameter: record_name}
      ui:
        # Content matching does not establish business-object identity.
        - check: objects_matching_count
          anchor: records.rows
          field: name
          value: {from_parameter: record_name}
          count: 1
```

The concrete cutover marker is a format identifier, not a package release or a
revision of the Scenario's acceptance intent.

The following rules are part of the approved expression:

- A step has one primitive action. There is no `action`, `type`, or `sequence`
  wrapper, no additional display-name field, and no `precondition` callback.
  `scenario` and step `id` remain stable identifiers.
- Logical `target` values map to product elements; selectors and mechanical
  interaction belong to the adapter. Mapping a click must not secretly perform
  another fill, navigation, or business preparation sequence.
- `do: wait` uses `duration` in milliseconds, for example `duration: 5000`.
  Core owns the bounded wait; it is not an assertion, a scheduler trigger, or
  permission to change a machine clock.
- A step may omit `expect`. The complete Scenario must contain at least one
  effective assertion; empty assertion containers do not satisfy that rule.
- Parameters are referred to with `{from_parameter: record_name}`. A later
  step may refer to `{from_step: submit, response_field: id}`. This reads the
  actual normalized runtime response, never the value written in an expectation.
  References must be validated, ordered, and resolved without scripts or a
  second user-managed binding alias layer. Mock and live response provenance
  must remain distinguishable.
- Preserve strict value semantics, including `false` versus `0` and `true`
  versus `1`. Request path segments remain explicit data, not expressions.
- Declared request-body fields are subset constraints. Additional transport
  fields do not automatically violate that declaration. Do not silently turn
  this into exact whole-body equality or let a mapper invent business inputs.

## Projection and adapter boundaries

One request declaration has two explicit interpretations: frontend/e2e verify
the outgoing UI request; backend constructs and sends the declared request
through its mapping. Projection selection belongs to the execution caller.
Backend execution does not perform or validate the UI actions; its result must
explicitly identify that UI evidence was not checked.

E2e must never compensate for an incorrect or missing UI request by sending a
correct HTTP request itself. No projection may invent missing business values,
responses, or evidence to obtain a pass. A missing capability must be visible,
not treated as success.

E2e reuses the relevant UI, request, response, and backend-state checks on
associated evidence; it does not have its own duplicate assertion area.
Contract checks compare declared provider compatibility against actual provider
recordings. They do not need a separate user assertion area and do not prove
whole-system equivalence or replace all e2e behavior. The current runner requires
backend when contract is selected; changing that recording source requires an
explicit decision, not an implicit fallback execution.

Adapters retain mechanical responsibilities: target/API mapping, session
handling, normalization, and evidence collection. Independent StateProbe and
Recorder ports need not be merged or removed. A trace observation is not, by
itself, proof of persistence, and correlated evidence is not automatically
independent evidence.

## Execution decisions

The maintainer approved the following API-only form. It does not change the UI
example or require UI Scenarios to add request actions for backend projection:

```yaml
- id: wait_for_export
  do:
    request:
      method: GET
      path: [exports, export-123, status]
  poll:
    on_timeout: FAIL
  expect:
    response:
      - check: field_equals
        field: state
        value: ready
```

### Declaration and references

The concrete cutover marker is `schema_version: 1`. UI actions keep scalar `do`;
API actions use exactly the one-key mapping
`do: {request: ...}` and may not also declare `expect.request`, target, value, or
duration. There is no implicit API action or action sequence.

Required metadata is schema_version, scenario, actor, and nonempty steps.
Description and the unique-key parameters mapping are optional. Existing
`grid: {level, module}` remains optional organizational metadata; requested
filters must not silently match a missing grid. Unknown/old declaration keys,
duplicate mapping keys, duplicate step IDs, and ambiguous references are errors.
The version is a strict integer, not a boolean. Preserve finite JSON-like values.
Open/click require target; fill requires target and value; wait requires finite
non-negative integer duration in milliseconds. Reject unrelated action keys.
An API command alone is not an assertion; at least one actual request constraint
or bounded assertion is required in the Scenario. There are no e2e/contract
assertion areas. UI count replaces n without changing equality/strict greater-than
semantics; backend_state retains its bounded span vocabulary.

References work in action values, path segments, body values, and supported
assertion values. A response source must be an earlier request-bearing step;
read its actual normalized response. Missing/null response fields produce ERROR
without a partial resolved mapping; false, zero, and empty strings remain valid.
Do not auto-add source assertions. Preserve per-segment URL encoding and typed
whole-value substitution; no expressions, interpolated strings, reference keys,
or user-managed bind aliases. Internal lowering may reuse existing models but
must not accept old YAML.

### Actions and traffic

One permit authorizes one UI primitive. An action envelope identifies execution,
step, action, and live/mock mode independently of traffic. Requests have separate
immutable identities and response pairing; one action may have zero to many.
Only traffic with a verifiable action association can satisfy expect.request.
First method/path match, current time window, or array order is insufficient.
Replay, swapped, and stale identities are protocol errors; unassigned traffic is
diagnostic only. Select the unique declared method/path target after association.
Missing or ambiguous targets cannot pass. Correctly associated requests with
wrong body values fail a request check. Maps use recursive subset comparison;
arrays require equal length/order with recursively strict elements; scalars require
equal type and value. Mappings nested in arrays retain recursive subset semantics.
Mapping must not invent undeclared business defaults.

The reference browser adapter establishes event/request lineage at creation and
pairs responses by request identity. Untracked async lineage stays unavailable,
never relabelled by arrival time. Completion barriers observe the actual operation
and render lifecycle, not expected content. This is bounded correlation, not
universal browser causality or malicious-adapter resistance. No private product
change is required by this protocol.

### Mock sources and projection scope

Frontend mocks come from explicit caller-supplied, inspectable fixtures or ordered
plans, including secondary routes. Preserve source and consumption evidence.
Never synthesize passing responses from expect, use hidden business defaults,
or pass unmatched mock traffic through to a real API. Fixtures are assumptions,
not backend proof; mock responses never become live provider recordings.

Backend sends do.request operations or projects a UI step's request constraint;
it never performs UI interactions and identifies UI checks as outside its scope.
Frontend/e2e use one shared UI loop. E2e may send explicitly declared do.request
via ApiDriver, never to repair a missing/incorrect UI request. Frontend mock does
not execute direct API actions: reject this capability before context creation.
Direct API actions with UI assertions are outside this first slice and must fail
capability preflight, not silently discard those assertions.

Contract continues consuming backend recordings without implicit backend runs.
Distinguish checks outside a selected projection from missing capabilities inside
it. Missing declared state evidence is not a pass. StateProbe stays independent,
called only for state checks with the selected real request trace. Requestless
state observation has no approved correlation source: explicitly reject it before
side effects, rather than borrowing an earlier trace.

For an explicit API call, a missing returned trace may use the core-generated
outgoing request trace only after strict request/response pairing. This is local
request correlation, not proof of server trace observation. Contradictory e2e API
traces remain errors; StateProbe still supplies actual facts. This does not relax
the separate action-origin checks for UI traffic.

### Completion, polling, and lifecycle

No-check actions may be COMPLETED with empty checks, not fabricated successes.
Backend UI-only steps are explicitly NOT_APPLICABLE. Neither status is an
assertion success. Projection PASSED requires actual checks without failures or
degradation; EMPTY/NOT_SELECTED cannot satisfy the strict gate. FAILED, ERROR,
and explicit SKIPPED block later steps. NOT_APPLICABLE cannot hide a missing
capability for an explicitly selected observation point.

Only explicit do.request GET steps may poll, with response stop assertions.
Keep PollConfig timing and FAIL/SKIP timeout behavior: immediate first attempt,
repeat until response predicates pass or timeout, then evaluate state against
the final response. Each attempt has its own trace/recording identity; only a
successful terminal attempt is final. Transport exceptions are ERROR, not blind
retries. Support backend and explicit API steps in e2e, never repeated UI clicks.
Wait is a core millisecond delay, not polling, a job trigger, or clock mutation.
The shared live UI loop retains its caller-configured state-observation timeout
and interval for all step counts; do not reintroduce the removed single-step
legacy timeout path. Backend state-helper defaults are unchanged in this slice.

Resolve references atomically before executing, retaining the sensitive top-level
isolated diagnostic mapping after subsequent errors. Preserve repr hiding,
exactly-once context cleanup, protected recording copies, Recorder exception and
order checks, and strict live-UI StateProbe trace validation. No generic approval
or serialization system is introduced.

## Coordinated implementation scope

| Area | Minimum change and reuse |
| --- | --- |
| Declaration model, loader, vocabulary, binding | Model primitive actions and optional expectations; validate the one-action and scenario-assertion rules; support direct parameter/prior-response references and retain strict typing. |
| Runner, shared UI orchestration, reports | Separate action completion from assertion success; retain fail-fast, blocked steps, context cleanup, sensitive binding boundaries, and honest projection results. Reuse one shared frontend/e2e loop. |
| Ports and reference adapters | Support requestless actions and correlated traffic without hidden workflows; make preparation explicit and mocks inspectable. Preserve authenticator, normalizer, state, and recording responsibilities. |
| Public examples, tests, and guides | Migrate the maintained examples and executable contract together; keep a real browser product acceptance path and negative controls. |

Only the new format needs support after the coordinated cutover. Old declarations
must be rejected explicitly rather than silently upgraded. No legacy adapter or
Scenario compatibility layer is required. Historical frozen evidence must not be
rewritten to look as though it used the new format; reproduce it with its recorded
baseline. Any non-public adapters and scenarios require their own separately
authorized migration outside this public change.

### Authoring UI withdrawn

On 2026-10-13 the maintainer withdrew the local draft workbench from this
delivery and requested its code, dedicated tests, and guide be removed.
Graphical authoring is deferred, not a current implementation priority.
This supersedes the original editor part of this task; it does not remove UI
actions, frontend/e2e projections, or real-browser product tests. The approved
YAML and the implemented core contract remain unchanged. Review the actual YAML
directly; declaration validation remains distinct from approval and execution.

## Acceptance evidence

- The approved example, requestless actions, and a later-step response reference
  load and execute under their explicitly supported projections. Empty scenarios,
  undefined/forward references, and multiple actions within one step are rejected.
- A zero-assertion step can complete without inventing a check; a whole Scenario
  without effective assertions cannot pass validation. Execution cannot become a
  green business verdict through absent evidence or an unselected projection.
- UI-request deviations cannot be repaired by backend calls during e2e.
  Multiple/late/background requests, replayed identities, and swapped evidence
  are covered by negative tests. Mock sources and non-live evidence are visible.
- Body subset matching, response references, strict types, content-versus-identity
  assertions, failure semantics, sensitive default representations, and fail-fast
  behavior have direct tests. Preserve retained contract, state, and polling
  behavior according to the completed implementation decisions above.
- A real-browser reference run exercises the explicit primitive steps and passes
  the full strict gate, `rep.status == "PASSED"`; an empty degradation list alone
  is not sufficient. Browser execution must not be silently skipped.
- CLI validation checks the final YAML, with no silent migration or added
  assertions. Public regression, lock, hygiene, and diff checks pass. The
  withdrawn authoring UI is not an acceptance requirement.
- Independent audit verifies both these requirements and public information
  provenance before architect acceptance. Green tests alone do not establish
  complete requirement coverage, usability gains, or submission authorization.

## Non-goals

No nested Scenario execution, second authoring language, general operation
registry, arbitrary expression engine, host-clock manipulation, cryptographic
approval/Merkle system, automatic approval propagation, or intent-governance
tree. No claims of complete business truth, malicious-adapter resistance, or
frontend/backend/contract equivalence to e2e are introduced by this task.
