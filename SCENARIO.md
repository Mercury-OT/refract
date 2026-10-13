# Refract Scenario Contract

A Scenario is a versioned acceptance baseline expressed as data: metadata,
parameters, and ordered primitive actions with expectations. It is not a complete
business truth or a script. Product preparation belongs in visible steps, not an
adapter's hidden workflow. Selectors, transport routing, session handling, and
truthful evidence normalization remain adapter responsibilities.

## Format and metadata

The executable format is `schema_version: 1`. This identifies the declaration
format, not a Scenario's content revision or approval. Unversioned declarations,
`version: 2`, and the former `inputs`, `intent`, `precondition`, and `bind` YAML
fields are rejected; no silent conversion or compatibility mode is provided.

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | strict integer `1` |
| `scenario` | yes | stable nonempty Scenario identifier |
| `description` | no | human-readable intent |
| `actor` | yes | identity or role resolved by the authenticator |
| `parameters` | no | mapping of declared data values |
| `grid` | no | organizational selector `{level, module}` |
| `steps` | yes | nonempty ordered list with unique step IDs |

Parameters contain finite JSON-like data, not scripts or generators. Unknown
fields, duplicate mapping keys, and invalid reference shapes fail validation.
A requested grid filter does not silently match a Scenario without that grid.

## One action per step

There is no `action`, `type`, or `sequence` wrapper. A step has one `id`, one `do`,
the applicable action fields below, and optionally `expect`.

| Action | Declaration | Meaning |
| --- | --- | --- |
| Open | `do: open`, `target` | open one logical page |
| Click | `do: click`, `target` | activate one logical control |
| Fill | `do: fill`, `target`, `value` | fill one logical input |
| Wait | `do: wait`, `duration` | core waits a nonnegative integer number of milliseconds |
| API request | `do: {request: {method, path, body?}}` | send the declared request |

Targets map to elements, not multi-action business scripts. A click must not
secretly navigate, fill fields, and submit. Wait does not trigger a scheduled
job, change the host clock, or assert success.

An API action stores its request under `do.request`, never under `expect`.
A UI action may declare `expect.request` to constrain the traffic it causes.
The same step cannot contain both request forms. Requests use an HTTP method,
an explicit list of logical path segments, and an optional body mapping.
Each path segment is encoded separately after resolving references.

One step may have no expectations. The entire Scenario must have at least one
effective request constraint or bounded assertion. An API command, wait, or
empty expectation container alone does not make a test.

## Expectations and projections

`expect` can contain `request` (a request mapping on UI actions), `ui`, `response`,
and `backend_state` (lists of bounded assertions). There are no separate e2e or
contract assertion areas.

| Projection | Execution and checks |
| --- | --- |
| `backend` | sends API actions or a UI step's declared request; checks response and declared state; does not perform or verify UI actions |
| `frontend` | performs UI primitives with explicit mock fixtures; checks UI, associated outgoing requests, and mock responses |
| `e2e` | performs UI primitives live, or explicitly declared API actions; reuses relevant checks on associated evidence |
| `contract` | compares declared response compatibility with backend recordings; sends no requests |

Projection selection belongs to the caller. Checks outside that projection must
be reported as such, not described as verified. Missing evidence or capability
within a selected projection is not a pass. E2e must never repair missing or
incorrect UI traffic by sending a correct API request itself. Contract requires
backend and does not implicitly execute it or prove whole-system equivalence.

This slice rejects frontend direct API actions, API actions with UI assertions,
and requestless backend-state observation before side effects. No previous trace
is borrowed to simulate requestless observation.

### UI vocabulary

The declaration calls this area `ui`; the evaluator and reports retain the
`frontend` observation-point name.

| Check | Parameters |
| --- | --- |
| `visible` | `anchor` |
| `count_gt` | `anchor`, `count` |
| `objects_matching_count` | `anchor`, `field`, `value`, `count` |
| `object_field_equals` | `anchor`, `id`, `field`, `value` |
| `no_anonymous` | `anchor` |

`visible` means at least one rendered object. `count_gt` means strictly more
than `count`; `objects_matching_count` means exactly `count` objects whose field
is present and equals `value`. Both identified and anonymous objects participate.
Counts do not establish identity. Use `object_field_equals` and `no_anonymous`
when business identity is part of the obligation.

`object_field_equals.id` must be a parameter or prior-response reference, not a
literal. Its `value` and matching-count `value` accept scalar literals or
references. Equality is type-strict: `false` is not `0`, and `true` is not `1`.
`no_anonymous` requires no rendered object at the anchor to lack reliable
business identity; it is not a user-authentication assertion.

### Request constraints

A UI step's `expect.request` constrains method, logical path, and declared body
fields. Mapping comparisons are recursive subsets: additional transport fields
are allowed. Arrays require equal length and order with type-strict recursive
elements; mappings inside arrays remain subsets. Scalars require identical types
and values. A mapper must not invent
undeclared business inputs to satisfy the constraint.

### Response vocabulary

| Check | Parameters |
| --- | --- |
| `success` | none |
| `failure` | none |
| `has` | `field` |
| `field_equals` | `field`, `value` |
| `field_absent` | `field` |
| `collection_matching_count` | `field`, `matching`, `count` |

`success` and `failure` check the normalized success indicator and cannot coexist
in a step. `failure` is a complete rejection assertion; add field checks for an
expected rejection reason. `has` checks presence. `field_equals` checks presence
plus exact type and value, using a scalar literal or reference. These are
normalized fields, not arbitrary raw JSON paths.

`field_absent` checks membership, not truthiness: a present null, zero, false,
empty string, list, or mapping fails. Failure details name the field, not its
value. Duplicate absence checks, or absence combined with `has`,
`field_equals`, or `collection_matching_count` on the same field, are invalid.

`collection_matching_count` checks an observed list of objects in one normalized
field. `matching` is a nonempty mapping of field names to scalar literals or
parameter/prior-response references. A member matches only if every named field
is present on that same member and strictly equals its expected value. Extra
fields are allowed; list order is irrelevant and duplicate members count
separately. `count` is an exact nonnegative integer, not a boolean or reference.

```yaml
- id: read_list
  do:
    request:
      method: GET
      path: [records]
  expect:
    response:
      - check: success
      - check: collection_matching_count
        field: records
        matching:
          id: {from_step: create, response_field: id}
          name: {from_parameter: record_name}
        count: 1
```

This fragment assumes an earlier request-bearing `create` step and a declared
`record_name` parameter. References read actual responses, not expectations.
Known nonscalar parameter values are invalid declarations; a runtime nonscalar
response reference produces `ERROR` before executing the step. Literal null or
a null parameter may be matched, but a missing member field is not null. Existing
missing/null prior-response reference errors are unchanged.

A missing field, non-list value, or any non-object list member fails, even when
count is zero. Only an actual empty list can establish zero without inspecting
members. Multiple constraints on the same collection are all retained. New
diagnostics report names, counts, and structural reasons, not matching values or
raw members. These checks inspect only the observed response/page; they do not
fetch other pages, infer UI identity, or prove database state. The normalizer
must preserve the observed collection, not select its first item or prefilter
it using expected values. No JSONPath or nested matching syntax is supported.

This is a normalized-only boundary. A normalizer can omit a raw response field;
absence from its field map is not proof that raw HTTP data contains no leak.
Trusted evidence, adapter conformance, and security verification remain separate.
Retained raw recordings may still contain sensitive data.

### Backend-state vocabulary

| Check | Parameters |
| --- | --- |
| `span_exists` | `span` |
| `span_attr` | `span`, `attr`, `op`, `value` |

`span_attr` uses `>`, `>=`, `<`, `<=`, or `==`; ordering requires a numeric
value. Supported reference comparisons use equality. StateProbe remains separate
and is called only for declared state checks against the selected real trace.
Live UI state facts must carry that same nonempty, type-strict trace ID. Missing
StateProbe is visible degradation. A span alone does not establish persistence;
shared trace correlation does not establish independent evidence.

An explicit API call is paired with its returned request/response at the driver
boundary. If that response has no trace ID, core may use the trace it put on the
strictly matched outgoing request as local correlation. This is not evidence
that the server echoed or observed that trace. A contradictory returned trace is
an error in e2e; UI traffic still needs its separate action-origin association.
State assertions still require actual StateProbe facts, not this fallback alone.

## Parameters and prior response values

The reference forms are `{from_parameter: record_name}` and
`{from_step: submit, response_field: id}`. They can occur in action values, path
segments, body values, and supported assertion values. A response reference names
an earlier request-bearing step and reads its actual normalized runtime response,
never its expected value. A source step need not assert `has`: preparation
requests may supply values without inventing checks.

Missing or null response fields produce `ERROR` atomically, with no partial
resolved mapping. Zero, false, and empty strings remain valid. No user-managed
binding aliases, expressions, arithmetic, concatenation, JSONPath, reference-valued
mapping keys, or coercion are supported. Frontend references read mock responses,
which remain distinguishable from live responses.

## Polling and outcomes

Only explicit API `GET` actions may declare `poll`; response assertions are the
stop predicate. Core sends the first attempt immediately, then repeats under the
caller's `PollConfig` timeout and interval. `on_timeout` is `FAIL` or `SKIP`.
Transport exceptions are `ERROR`, not blind retries. Each attempt has a distinct
trace and recording; only a successful terminal attempt is final. State checks
evaluate against that response.

```yaml
schema_version: 1
scenario: demo.export_ready
actor: user
steps:
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

Polling never repeats UI clicks. Eventual-consistency observation may repeat
StateProbe calls without replaying an action. Backend and e2e support explicit
API polling; frontend rejects it before context creation.
Live UI state observation uses the caller's timeout/interval budget, including
single-step runs through the shared loop. The backend state helper retains its
separate existing default observation budget; response polling does not imply
that every projection shares one combined deadline.

Steps run in order. `FAILED`, `ERROR`, and `SKIPPED` block later steps.
A no-check action can be `COMPLETED`; a backend UI-only step is
`NOT_APPLICABLE`. These have empty checks and are not assertion successes.
Projection `PASSED` requires actual checks without failure or degradation.
`EMPTY` and `NOT_SELECTED` cannot satisfy the strict gate.

## UI evidence and mock sources

Frontend and e2e share one orchestration loop for every step count. Core
authorizes one primitive, checks evidence, resolves later values, and decides
whether the next action may run. One authenticated UI context is reused and
closed exactly once. There is no legacy `run_intent()` workflow fallback.

Action identity is separate from traffic: an action may produce zero to many
requests. Each associated request has an immutable ID and response pairing.
Core checks run, step, action, mode, permit, and traffic correspondence, then
selects the unique declared method/path target. Missing or ambiguous target
traffic cannot pass. Stale, swapped, or replayed identity is a protocol error;
correctly associated traffic with a wrong body fails the request check.

Background/unassigned traffic is diagnostic only. First method/path match,
arrival window, and list position do not establish action ownership. The
reference browser adapter captures bounded event/request-creation lineage;
untracked async origins remain unavailable. Completion follows actual operation
and render lifecycle, not the appearance of expected content. This is not
universal browser causality or protection from a malicious adapter fabricating
an internally consistent bundle.

Frontend mocks are explicit caller-supplied ordered fixtures, including initial
and secondary routes. Source and consumption remain visible. Mocks are not
synthesized from `expect`; unmatched traffic cannot silently reach a live server.
Mock responses never become live provider recordings. Recorder failures are
errors; returned live recordings are verified, not trusted by list order alone.

Rendered anchors contain `identified` objects with nonempty string IDs and field
maps, and `anonymous` objects with field maps and no ID. Values are JSON scalars.
Adapters retain unidentified objects rather than dropping them. Content matching
must not guess identity from names, row order, or response order.

## Reports and sensitive data

`StepResult.resolved_bindings` remains a diagnostic view even though YAML no
longer declares `bind`. It is filled after complete resolution, retained after
later failure/error, and empty on resolution failure or blocked steps. It does
not affect equality, checks, status, or gates. It is a
**top-level-container-isolated diagnostic view**, not an immutable snapshot:
nested objects may remain shared.

Refract does not automatically print or serialize this field. Default step and
nested run representations hide it; provider recordings and sensitive
permit/evidence payloads are also hidden. `sensitive=True` is metadata, not a
security mechanism. `dataclasses.asdict()` and generic third-party serializers
can still expose values. Reports, permits, fixtures, and evidence are sensitive.
Machine exports need explicit allowlists or redaction, never direct generic
serialization of these objects.

The only complete strict execution gate is:

```python
assert rep.status == "PASSED"
```

`rep.passed` can include `DEGRADED`. `rep.degradations() == []` is supplementary,
not a standalone gate: failed, empty, or unselected reports may have none.
A pass covers performed checks, not omitted obligations or the correctness and
completeness of the human-approved baseline.

## Contract identity

Contract consumes backend recordings without sending requests. Its identity is
`(step_id, method, declared template_path)`; bound and actual paths remain
evidence, not replacements for declared identity. Only final polling recordings
contribute. Response requirements retain success/failure/don't-care, required
fields, expected values, forbidden fields, and all collection matching
constraints. Collection checks evaluate final provider collections with the
same strict matching rules and actual provider-reference values; contract does
not reduce them to presence checks. Empty consumer checks do not
produce a passing contract. Compatibility does not prove UI or full business
acceptance.

## Worked UI example

This synthetic declaration makes each interaction visible. Targets and fields
need truthful mappings; frontend execution also needs explicit mock data.

```yaml
schema_version: 1
scenario: demo.record_create
description: Create a record and check response and rendered content.
actor: editor
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
        - check: objects_matching_count
          anchor: records.rows
          field: name
          value: {from_parameter: record_name}
          count: 1
```

## Validation and review

`refracto validate` checks declarations, not product behavior or human approval.
Missing actions, invalid references, unsupported vocabulary, duplicate identities,
and assertion-free Scenarios fail loudly. Review and approve the actual YAML;
validation must not silently add checks or convert old files. There is currently
no supported graphical Scenario authoring tool in this repository.

Implementation lives in `declaration/model.py`, `loader.py`, `vocabulary.py`,
and `binding.py`, and is exercised by projection and adapter tests.
Disagreement between this document and implementation is a defect to resolve,
not permission to silently alter acceptance intent.
