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
| `results` | no | named aliases of this Scenario's own observed response fields |

Parameters contain finite JSON-like data, not scripts or generators. Unknown
fields, duplicate mapping keys, and invalid reference shapes fail validation.
A requested grid filter does not silently match a Scenario without that grid.

## One action per step

There is no `action`, `type`, or `sequence` wrapper. An executable leaf step has
one `id`, one `do`, the applicable action fields below, and optionally `expect`.
A static include is a composition node expanded into these same leaves before
execution, not a multi-action adapter primitive.

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
| `status_equals` | `value` |
| `status_in` | `values` |
| `has` | `field` |
| `field_equals` | `field`, `value` |
| `field_absent` | `field` |
| `collection_matching_count` | `field`, `matching`, `count` |

`success` and `failure` check the normalized success indicator and cannot coexist
in a step. `failure` means that indicator is false; it does not establish why a
request was rejected or whether an authorization decision was reached. Add the
actual response and state requirements needed for the intended obligation.
`has` checks presence. `field_equals` checks presence
plus exact type and value, using a scalar literal or reference. These are
normalized fields, not arbitrary raw JSON paths.

`status_equals` checks one exact HTTP status; `status_in` checks membership in an
explicit set. `value` is a literal integer from 100 through 599. `values` is a
nonempty list of distinct literal integers in the same range. Booleans, floats,
strings, null, references, and extra parameters are invalid. List order is kept
for review but does not affect membership. Each step may have at most one of
these HTTP-status checks, with no duplicates. Other response checks may coexist;
HTTP status is not used to infer the normalized success indicator.

These are alternative fragments inside a request-bearing step's
`expect.response` list:

```yaml
- check: status_equals
  value: 201
```

```yaml
- check: status_in
  values: [200, 204]
```

The observed value is captured from the selected recording before normalization,
not taken from a normalizer's status, raw-response alias, or field map. Missing
or malformed status evidence cannot pass. Frontend checks use explicit mock
responses; backend and live e2e use their actual associated responses. Polling
checks each attempt and keeps its existing final/timeout rules. A matching HTTP
status alone does not prove a rejection mechanism or complete business success.
See the executable [create/delete example](examples/documents/scenarios/http_status_create_delete.yaml)
for 201 creation and an empty 204 deletion without a synthetic status field.

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

The local reference forms are `{from_parameter: record_name}` and
`{from_step: submit, response_field: id}`. An included Scenario's public result
uses `{from_step: setup, result: record_id}` as described below. They can occur in action values, path
segments, body values, and supported assertion values. A response reference names
an earlier request-bearing step and reads its actual normalized runtime response,
never its expected value. A source step need not assert `has`: preparation
requests may supply values without inventing checks.

Missing or null response fields produce `ERROR` atomically, with no partial
resolved mapping. Zero, false, and empty strings remain valid. No user-managed
binding aliases, expressions, arithmetic, concatenation, JSONPath, reference-valued
mapping keys, or coercion are supported. Frontend references read mock responses,
which remain distinguishable from live responses.

## Including a pinned, reviewed Scenario

A Scenario may include all steps of a local child with the same `actor`. The
child must independently validate, contain an effective assertion, and have no
include of its own. No recursion, dynamic target, partial inclusion, assertion
override, actor switch, or execution cache is supported.

The include step accepts only `id`, `do: {include: <literal Scenario ID>}`, and
optional `with`. For example, in a parent declaring a `record_name` parameter:

```yaml
- id: setup
  do:
    include: demo.create_record
  with:
    record_name: {from_parameter: record_name}
```

`with` may override only parameters already declared by the child. Omitted names
use child defaults; null is an ordinary value, not a required-parameter marker.
Values use the existing literal, `from_parameter`, and earlier `from_step` forms.
Caller references are checked at the include position, while child-internal
references remain local. Runtime responses are not read during loading. Each
invocation has isolated parameters and steps; literal objects resembling reference
syntax remain data. No additional parameterized positions are introduced.

### Named results

A child explicitly names the observed values it offers to callers:

```yaml
results:
  record_id:
    from_step: create_request
    response_field: itemId
  record_name:
    from_step: create_request
    response_field: name
```

This is a top-level mapping in the child. Each source has exactly `from_step`
and `response_field`, both non-blank strings. It names a local request-bearing
step, including a UI step with `expect.request`, and an actual normalized response
field. Different names may refer to the same or different local steps. Unknown,
requestless, include, expanded child, and other result sources are rejected.
`results` may be omitted or empty. Names are unique non-blank strings interpreted
literally, not paths. Results are aliases, not executable return actions.

A later parent step uses `{from_step: setup, result: record_id}`. `setup` is the
earlier include step; `record_id` is a declared child result. This form works in
every existing value position, including another include's `with`. Unknown names,
forward/self references, `result` on an ordinary step, or mixing `result` with
`response_field` are errors. An ordinary object `{result: ok}` remains literal
data; `result` alone is not a reference marker. Literal parameter objects are
never reinterpreted as references after substitution.

The caller cannot access `{from_step: setup/create_request, response_field: itemId}`
or other internal child fields directly. Ordinary local response references
remain supported. Qualified IDs such as `setup/create_request` are retained only
for execution, reports, and the explicit expanded review view. Ordinary source
step IDs within a composition may not contain `/`.

The loader translates result references to existing response bindings. There is
no extra runtime result store, computation, re-export, or deeper inclusion. An
internal step can be renamed without editing caller YAML when its result mapping
is updated, but the changed child still needs a reviewed sidecar pin update.
Removing or renaming a public result requires caller changes and review.

Results never count as assertions or manufacture evidence. Unused results are
not read or checked implicitly. A consumed missing/null field causes the existing
atomic binding `ERROR` before the consuming action; falsy values survive subject
to that position's type rules. Even if the source already ran successfully,
FAILED/ERROR/SKIPPED in any later child step blocks the parent consumer. Every
invocation reads its own current-run responses; frontend mock values remain mock
values. No values are borrowed across projections or prior runs.

### Dependency sidecar

For a parent `create_read.yaml`, dependencies are pinned in the regular local
file `create_read.includes.json` beside it. The JSON object has exactly
`manifest_version` (integer `1`) and `scenarios` (a mapping). Each mapping key is
an included Scenario ID; its value has exactly `path` and `sha256` strings.
The ID must equal the child file's declared `scenario`. Entries must exactly
match the parent's distinct include targets. Duplicate keys, unknown fields,
missing/unused entries, and multiple IDs aliasing one file are errors.

`path` is a literal relative file path inside the parent's directory, independent
of the current working directory. Absolute paths, parent traversal, URI schemes,
symlinks, globs, and variable expansion are rejected. There is no repository scan,
network resolution, inline pin alternative, or version fallback. Non-include
Scenarios do not consult sidecars.

`sha256` is 64 lowercase hexadecimal digits hashing the entire child file bytes,
including comments and line endings. Hashing and parsing use the same read buffer.
A change requires an explicit reviewed pin update; it cannot be silently accepted.
All dependencies are validated before any authentication, waits, requests, or UI
actions. Limits are 64 distinct child files and 1,000 expanded leaves, inclusive;
exceeding a limit fails rather than truncating the plan.

A hash proves content agreement, not human approval. The existing review process
must cover the child, parent, and sidecar together. Unchanged child internals can
reuse prior review, but caller parameters can change assertion expectations and
still need review, as do the parent's order, purpose, and overall obligations.
Every include executes anew; prior passing evidence is not reused as a result.

### Execution and review view

Inclusion expands symbolically into the existing ordered execution model. The
parent retains its actor, metadata, grid selection, adapters, and projections.
Child grid metadata cannot silently filter steps. Each UI projection retains one
session/context. All child actions and checks remain present; unsupported expanded
flows still fail the existing projection checks before side effects.

FAILED, ERROR, and SKIPPED block later child and parent leaves. Inclusion is not
a transaction: a runtime-only argument error occurs before its consuming action,
and earlier actions may already have run. There is no rollback or hidden setup.
No parent-only assertion is mechanically required when the child already supplies
effective checks, but that does not establish the parent's complete business goal.

`refracto validate <parent.yaml> --expand` explicitly prints the verified flat
review plan and its sources. It preserves symbolic response references and shows
declared public result names and their source mappings. It never runs adapters,
and emits no partial plan when validation fails. This is a review
view, not another authoring format. It can display literal declaration data,
including `with` values; its confidentiality matches the source files. It never
contains runtime response values. Default validation remains a concise summary.

Qualified leaf IDs remain in reports and contract identity. The loaded Scenario
and RunReport expose `source_lookup`, a diagnostic map with source Scenario ID, original
step ID, include step ID, and source-byte SHA-256. This does not affect equality,
status, or execution and is hidden from default repr. `localize()` still returns
failed checks in its existing tuple shape; ERROR/BLOCKED are inspected through
StepResult, with the same source lookup. No approval status is inferred.

Maintained executable examples are the [API parent](scenarios/demo_include_items.yaml)
with its [pin file](scenarios/demo_include_items.includes.json) and the
[UI parent](scenarios/demo_include_items_ui.yaml) with its
[pin file](scenarios/demo_include_items_ui.includes.json). Their children live in
`scenarios/include_shared/`. The API example runs backend plus contract; the UI
example runs frontend with explicit mocks or live e2e. The selected projection
does not change which child bytes were pinned.

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
contribute. Response requirements retain success/failure/don't-care, an optional
exact HTTP status or allowed status set, required
fields, expected values, forbidden fields, and all collection matching
constraints. Collection checks evaluate final provider collections with the
same strict matching rules and actual provider-reference values; contract does
not reduce them to presence checks. HTTP-status requirements use the original
recording status, independently of normalized success/failure; missing, malformed,
or nonmatching required status is a mismatch. Normalization receives an independent
copy, so it cannot rewrite the source recording's status or identity. Contract
uses the same backend evidence, not an independent source. Empty consumer checks do not
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

For read-only comparison of a changed child and its current callers, see the
[shared Scenario impact review guide](docs/impact-review.md). This does not
change declaration syntax, approve changes, update pins, or execute Scenarios.

`refracto validate` checks declarations, not product behavior or human approval.
Missing actions, invalid references, unsupported vocabulary, duplicate identities,
and assertion-free Scenarios fail loudly. Review and approve the actual YAML;
validation must not silently add checks or convert old files. There is currently
no supported graphical Scenario authoring tool in this repository.

Implementation lives in `declaration/model.py`, `loader.py`, `vocabulary.py`,
and `binding.py`, and is exercised by projection and adapter tests.
Disagreement between this document and implementation is a defect to resolve,
not permission to silently alter acceptance intent.
