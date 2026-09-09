# Refract Scenario Contract

A scenario is the single source of truth for Refract.

It is a pure data declaration that describes:

* who is acting
* under which grid cell the scenario should run
* optional preconditions and inputs
* one or more steps
* what must hold at each observation point

A scenario does not contain selectors, sleeps, imperative logic, or product-specific implementation details.

## Supported Forms

Refract supports two forms:

| Form | Selector | Meaning |
|---|---|---|
| v1 | no `version` field | legacy flat scenario, normalized to one implicit step |
| v2 | `version: 2` | ordered `steps` list |

Internally, execution is step-based.

## Top-Level Fields

| Field | Required | Meaning |
|---|---|---|
| `scenario` | yes | stable scenario id |
| `grid` | yes | execution grid selector: `{level, module}` |
| `actor` | yes | role or identity used by the adapter |
| `version` | v2 only | currently `2` |
| `precondition` | no | list of `{ref: ...}` references |
| `inputs` | no | ordered single-key input mappings |
| `intent` | no | human-readable scenario intent |
| `expect` | v1 only | flat assertions |
| `steps` | v2 only | ordered step list |

## Step Fields

Each v2 step may contain:

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | unique step id within the scenario |
| `request` | yes | request template: `{method, path, body?}` |
| `bind` | no | cross-step binding from prior normalized response fields |
| `poll` | no | polling policy |
| `expect` | no | assertions for this step |

## Observation Points

A step can assert three observation points directly:

* `frontend`
* `response`
* `backend_state`

For v1, `request` also appears under `expect`. For v2, request ownership is carried by the step's own `request` field.

## Bounded Vocabulary

### frontend

| check | params |
|---|---|
| `visible` | `anchor` |
| `count_gt` | `anchor`, `n` |
| `object_field_equals` | `anchor`, `id`, `field`, `value` |
| `no_anonymous` | `anchor` |

`object_field_equals` selects one identified business object at `anchor` and
compares one of its fields with exact type and value equality. Its `id` must be
one of these data-only references; a literal id is rejected during scenario
loading:

* `{from_input: key}` — exactly one top-level input with that key
* `{from_bind: key}` — a binding declared by the current step

Its `value` may be a YAML/JSON scalar literal or either reference form above.
`no_anonymous` requires the anchor to contain no rendered objects whose business
identity could not be determined.

`visible` and `count_gt` retain their existing meanings. Their count is the
total number of identified and anonymous objects at the anchor, and `visible`
is true when that total is greater than zero. The e2e projection uses the same
frontend evaluation rules.

### request

| check | params |
|---|---|
| `request` | `method`, `path` |

Optional v1 param:

* `async`

### response

| check | params |
|---|---|
| `success` | none |
| `failure` | none |
| `has` | `field` |
| `field_equals` | `field`, `value` |
| `field_absent` | `field` |

`success` requires the normalized response's success indicator to be true;
`failure` is its exact opposite and requires that indicator to be false. A
response expectation may declare either one, but not both: declaring `success`
and `failure` in the same step is rejected when the scenario is loaded. A
`failure` assertion is complete on its own and can also be combined with
`field_equals` to require both rejection and the expected reason.

`field_equals` requires the normalized response to contain `field` and for its
value to equal the declared expected value with exact type and value equality.
Its `value` is one of:

* a YAML/JSON scalar literal (`null`, boolean, number, or string)
* `{from_input: key}` — exactly one top-level input with that key
* `{from_bind: key}` — a binding declared by the current step

References are data-only. They do not support expressions, JSONPath,
arithmetic, concatenation, or coercion.

`field_absent` requires `field not in normalized_response.fields`. A present
field fails the assertion regardless of whether its value is `null`, `0`,
`false`, an empty string, an empty list, or an empty mapping. Failure details
name only the unexpected field and never include its value. Within one response
expectation, duplicate `field_absent` declarations for the same field are
invalid, as are `field_absent` combined with `has` or `field_equals` for that
field. A negative assertion does not guarantee field presence and therefore
cannot provide a later step's binding source.

The evidence boundary is intentionally narrow: `field_absent` observes
`NormalizedResponse.fields`, not the raw HTTP JSON. It proves only that the
field is absent from the normalized response surface exposed by the adapter. A
`ResponseNormalizer` may filter a field that was present in the raw response,
so this assertion alone cannot prove that a production HTTP response contains
no leaked data. It does not close the need for trusted evidence, adapter
conformance, E-7, or a security extension. Raw provider recordings retained in
reports may also still contain sensitive data; this change does not expand the
handling of that existing risk.

### backend_state

| check | params |
|---|---|
| `span_exists` | `span` |
| `span_attr` | `span`, `attr`, `op`, `value` |

## Binding Rules

Bindings are explicit references from a later step to a prior step.

A binding:

* must reference a prior step id
* must reference a field explicitly guaranteed by that source step through a
  response `has` or `field_equals` assertion
* substitutes path placeholders and whole-value body placeholders
* does not support expressions, arithmetic, or inline interpolation

## Polling Rules

Polling is step-local.

* currently GET-only
* stop condition is the step's `expect.response`
* `on_timeout` supports `FAIL` and `SKIP`

Because the full response assertion list is the stop condition,
`field_equals` polling waits for the declared value rather than stopping as
soon as the field appears.

## Execution Semantics

* steps run in order
* execution is fail-fast
* blocked later steps become `BLOCKED`
* step status is first-class

Single-step e2e continues to use exactly one legacy
`UiDriver.run_intent(..., mock=None)` call, even when the adapter also offers
stepwise execution. Multi-step e2e requires a `StepwiseUiDriver` that explicitly
reports `supports_stepwise_mode("live")`. A legacy or mock-only adapter reports
`multi-step e2e live capability not supported` before authentication,
preconditions, context creation, or UI actions.

The frontend projection keeps the existing single-step `UiDriver.run_intent()`
path unchanged. A multi-step frontend scenario requires the optional
`StepwiseUiDriver` capability. A legacy-only UI adapter reports
`multi-step UI capability not supported` before opening a UI context or
performing an action; the core never loops over `run_intent()` as a substitute.

For supported multi-step frontend runs, the core opens one UI context, reuses it
for every authorized step, and closes it exactly once. Steps are fail-fast:
after `FAILED`, `ERROR`, or `SKIPPED`, every later step is `BLOCKED` and the
adapter receives no further action permit. A context-close failure is reported
as a structured `ERROR` on the last non-blocked step. Multi-step frontend
polling is not supported and is rejected before the context is opened; the core
does not simulate polling by repeating a UI action.

Possible step outcomes include:

* `PASSED`
* `FAILED`
* `SKIPPED`
* `BLOCKED`
* `ERROR`

### Binding Diagnostics and Sensitive Report Data

Backend, stepwise-frontend, and stepwise-e2e step results expose
`StepResult.resolved_bindings` for diagnosing cross-step identity and
correspondence problems. The field is diagnostic only:
it does not participate in Oracle evaluation, status calculation, report
equality, or quality gates.

Those projections fill the field only after every binding for that step resolves
successfully. It remains `{}` for steps without bindings, binding-resolution
errors, blocked steps, legacy frontend/e2e results, and contract results.
If binding succeeds, the values remain available even when later execution,
normalization, evidence validation, checks, or polling produce `ERROR`,
`FAILED`, or `SKIPPED`.

`resolved_bindings` is a **top-level-container-isolated diagnostic view**: the
filling projection makes a shallow copy of the mapping used for execution. The mapping
objects are distinct, but nested lists or dictionaries may still be shared. It
is not an immutable snapshot.

Binding values may contain sensitive data. Refract itself does not print or
serialize this field, and neither `repr(StepResult)` nor the nested
`repr(RunReport)` includes it. The dataclass field metadata contains
`sensitive=True`, but that label is not a security mechanism. In particular,
`dataclasses.asdict()` and general-purpose third-party serializers still collect
the field. Consumers must treat every report object as potentially sensitive.
Stepwise UI permits and evidence can also contain sensitive bound paths,
bindings, mock bodies, rendered data, requests, responses, and diagnostic
traffic. Refract does not proactively print or generically serialize these
objects, and their sensitive payload fields are excluded from ordinary
`repr()`. Provider recordings are likewise excluded from the default
`repr(DomainResult)` and nested `repr(RunReport)`. Nevertheless,
`dataclasses.asdict()` and general-purpose serializers can still collect all of
these values. Reports, permits, and evidence must all be treated as potentially
sensitive. The future C-13 machine-export path must use an explicit field
allowlist or an explicit redaction policy; it must not directly serialize a
report, permit, or evidence object.

### Strict Quality Gates

`rep.passed` being true does not guarantee that every declared assertion ran.
When an optional port such as `StateProbe` is unavailable, the affected
assertions are recorded as skipped, the report status is `DEGRADED`, and
`rep.passed` may remain true.

A strict quality gate has one complete condition:

```python
assert rep.status == "PASSED"
```

An empty degradation list is useful as a supplementary diagnostic or an
additional assertion:

```python
assert rep.degradations() == []
```

It must not be used as a gate on its own. A `FAILED`, `EMPTY`, or
`NOT_SELECTED` report can also have no degradations. The status assertion is
the gate; the degradation assertion only adds confirmation that no declared
capability was skipped.

This is the current integration rule; it does not replace a future, clearer
core-level quality-gate API.

## UiDriver Rendered-Object Contract

`UiResult.rendered` is a partial mapping from anchors to business objects. Each
anchor has this shape:

```python
{
    "identified": [
        {"id": "business-id", "fields": {"name": "example", "count": 3}},
    ],
    "anonymous": [
        {"fields": {"name": "unidentified"}},
    ],
}
```

The rules are:

* every `identified` entry has a non-empty string `id` and a `fields` mapping;
* every `anonymous` entry has only a `fields` mapping and no `id` key;
* both lists may be empty;
* field names are opaque to the core and field values are JSON scalars;
* adapters must retain unidentified objects in `anonymous` rather than dropping
  them.

The adapter owns translation from the product surface to business ids and
scalar fields. Refract's core neither interprets field-name semantics nor
receives product-specific location concepts.

This structure replaces the earlier per-anchor `{visible, count, text}` shape
and is a breaking `UiDriver` port-contract change. Third-party UI adapters must
be updated before using this version.

## Stepwise UI Capability and Evidence Identity

`StepwiseUiDriver` is an independent, optional port. Capability detection is an
explicit `isinstance(ui, StepwiseUiDriver)` check; having coincidentally named
methods is not sufficient. Existing adapters need only continue implementing
`UiDriver.run_intent()` for single-step frontend and e2e runs.

Core owns one shared multi-step orchestration loop for frontend mock and e2e
live. It authorizes exactly one semantic action at a time, validates and
evaluates that action's evidence, updates binding inputs, and only then decides
whether the next action may run. Each projection execution receives a new
execution id and 32-byte random signing secret. Each step receives distinct
action and request ids, attempt index zero, a W3C `traceparent`, its declared and
bound path identities, resolved bindings, and a mode. Frontend permits carry
that step's synthesized mock response; live permits carry `mock_response=None`.
The permit token is HMAC-SHA256 over the canonical execution/action/request/
step/attempt/mode/method/path/trace identity. Frontend mock responses are built
per step and carried by permits; they are not stored in a global
`(method, path)` map, so repeated endpoints retain declaration order and distinct
responses.

Frontend and e2e remain separate physical projections. If both are selected in
one `run_scenario()` call, frontend opens its own mock context and e2e opens its
own live context. Within either projection, every step performs one semantic
action exactly once and all steps reuse that projection's authenticated session
and UI context. E2e authentication runs once, followed by each declared
precondition in order, before the context is opened. Missing or failing
precondition resolution becomes a structured `ERROR` with later steps
`BLOCKED`; no UI action or provider recording is produced.

The adapter returns either one completed `UiActionEvidence` or one non-empty
skip reason. Completed evidence must echo the permit identity and contain one
primary final request/response pair plus the current rendered surface. The four
e2e observation points—frontend, request, response, and backend state—are
evaluated for that single action and its trace; they are not obtained by
replaying the action. Core checks the token, step and run identities, declared
and bound paths, trace, final marker, request/response value correspondence, and
(in mock mode) mock body before normalization. Only that verified primary
response can be recorded or feed a later bind.

Path identity has three distinct layers. `template_path` is the declaration;
`bound_logical_path` is the template after bind substitution; and `actual_path`
is what the browser or transport boundary observed. The primary
`RequestSpec.path` must equal the bound logical path. The actual path may add a
leading slash or product base path, but it must be non-empty and must agree
between action evidence and its `RecordedResponse`. This lets adapter mapping
remain outside the core without confusing logical and transport evidence.

One action may expose one permit-correlated primary final request/response and
additional uncorrelated diagnostic traffic. Diagnostics—even a request with the
same method and path—cannot satisfy assertions and are never written to the
provider `Recorder`. A delayed prior response may remain diagnostic; traffic
that reuses the current permit's trace correlation is a protocol error, as is a
second current-correlated primary (retry is not supported). The core records
only fully verified live primary responses and verifies the Recorder's returned
count, identity, and order rather than trusting its list order.

`StateProbe` remains a separate port and is called by core only when the current
step declares `backend_state`. It receives the verified primary response's
permit trace id. Every returned `StateFacts`, including every eventual-
consistency polling observation, must have the same non-empty, type-strict trace
id. Missing `StateProbe` remains a visible degradation: the step may continue,
but the final report cannot be strictly `PASSED`. The UI driver and
`UiActionEvidence` do not carry backend state facts.

Multi-step UI/business-response polling remains unsupported and is rejected
before authentication or any action; core never repeats a click or permit to
simulate it. Backend-state eventual-consistency polling is different: it may
repeat `StateProbe.observe()` after one completed action, while the UI action,
business request, and permit still occur exactly once.

This protocol detects contradictory identity, mismatches, and replay across
steps or runs. It does not make an untrusted adapter incapable of fabricating an
internally consistent evidence bundle, and it does not make `StateProbe` an
independent or unforgeable trust root. Product-specific actions, navigation,
controls, and traffic capture remain adapter responsibilities; core does not
infer a UI action from an HTTP method or path.

## Contract Projection Identity

The contract projection consumes recordings produced by the backend projection;
it does not execute requests on its own.

For both static and templated multi-step requests, consumer and provider entries
are matched by:

* step id
* request method
* the declared request path template

The path after binding and the adapter-resolved path remain recording evidence,
but do not replace the declared template as contract identity. For a polled step,
only the recording marked as final contributes to the provider contract.

## Worked Example

A minimal public example stays product-neutral by using the demo namespace:

```yaml
scenario: demo.item_update
grid:
    level: regression
    module: demo
actor: user
precondition:
    - ref: item_exists
inputs:
    - new_name: renamed
intent: rename an existing item
expect:
    request:
        - check: request
          method: PUT
          path: items
    response:
        - check: success
        - check: has
          field: itemId
    backend_state:
        - check: span_exists
          span: item.update
        - check: span_attr
          span: item.update
          attr: row_count
          op: ">"
          value: 0
```

Note two things this example models:

* every observation point holds a **list** of assertions, including `request`;
* the declared `path` is the **logical** template (`items`), not a concrete resource
  path. Mapping it to the actual path the product serves is the adapter's job.

## Validation

Scenario loading is fail-loud.

Typical validation failures include:

* unsupported version
* malformed top-level structure
* unknown fields
* invalid assertion terms
* missing required params
* duplicate step ids
* invalid or unused bindings
* malformed placeholders
* invalid polling configuration

## Public Reference

The code-level sources of truth are:

* `refracto/declaration/model.py`
* `refracto/declaration/loader.py`
* `refracto/declaration/vocabulary.py`
* `refracto/declaration/binding.py`

If this document and the implementation differ, the implementation wins.
