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

### backend_state

| check | params |
|---|---|
| `span_exists` | `span` |
| `span_attr` | `span`, `attr`, `op`, `value` |

## Binding Rules

Bindings are explicit references from a later step to a prior step.

A binding:

* must reference a prior step id
* must reference a field explicitly declared by that source step through `response: {check: has, field: ...}`
* substitutes path placeholders and whole-value body placeholders
* does not support expressions, arithmetic, or inline interpolation

## Polling Rules

Polling is step-local.

* currently GET-only
* stop condition is the step's `expect.response`
* `on_timeout` supports `FAIL` and `SKIP`

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

## Worked Example

A minimal public example stays product-neutral by using the demo namespace:

```yaml
scenario: demo.item_update
grid:
    level: regression
    module: demo
actor: user
intent: rename an existing item
expect:
    request:
        check: request
        method: PUT
        path: items/1
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
          op: gt
          value: 0
```

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
