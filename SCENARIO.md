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
| `has` | `field` |
| `field_equals` | `field`, `value` |

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

Possible step outcomes include:

* `PASSED`
* `FAILED`
* `SKIPPED`
* `BLOCKED`
* `ERROR`

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
