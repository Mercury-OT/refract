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

The frontend and e2e projections currently support single-step scenarios only.
A multi-step frontend or e2e scenario is reported as unsupported rather than
partially executed.

Possible step outcomes include:

* `PASSED`
* `FAILED`
* `SKIPPED`
* `BLOCKED`
* `ERROR`

### Strict Quality Gates

`rep.passed` being true does not guarantee that every declared assertion ran.
When an optional port such as `StateProbe` is unavailable, the affected
assertions are recorded as skipped, the report status is `DEGRADED`, and
`rep.passed` may remain true.

A strict quality gate should require either:

```python
assert rep.status == "PASSED"
```

or explicitly reject every reported degradation:

```python
assert rep.degradations() == []
```

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
