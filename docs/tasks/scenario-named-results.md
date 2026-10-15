# Named Scenario results: approved implementation specification

## Authority, scope, and starting point

The maintainer approved the parent/child YAML below and multiple named results,
then authorized specification, development, independent audit, and local
acceptance. No staging, commits, pushes, or submission are authorized. Private
workspaces and their evidence remain untouched. Sources are the public code,
public Demo, and the approved product-neutral expression only.

This builds on the locally accepted, unsubmitted one-level include change over
main `9bebfa7559bfc22e7121bc31b1945e803676a1f8`; that dirty working tree is the
starting implementation, not an unrelated change to discard. The earlier
[acceptance record](scenario-include-acceptance.md) remains a historical snapshot.
This specification supersedes only the earlier include specification's exposed
child-step interface and its exclusion of named outputs. Same actor, one-level
inclusion, sidecar pins, limits, fail-fast, and existing port boundaries remain.

## 1. Approved expression

Child `shared/create_item.yaml`:

```yaml
schema_version: 1
scenario: shared.create_item
description: Create and check one item, exposing two observed response fields.
actor: user
parameters:
  item_name: Default record
steps:
  - id: create_request
    do:
      request:
        method: POST
        path: [items]
        body:
          name: {from_parameter: item_name}
    expect:
      response:
        - check: success
        - check: has
          field: itemId
        - check: field_equals
          field: name
          value: {from_parameter: item_name}
      backend_state:
        - check: span_exists
          span: item.create
# Names are the child's public interface, not executable return statements.
results:
  record_id:
    from_step: create_request
    response_field: itemId
  record_name:
    from_step: create_request
    response_field: name
```

Parent `create_update_read.yaml`:

```yaml
schema_version: 1
scenario: demo.create_update_read
description: Create, update, then check the same item in the returned list.
actor: user
parameters:
  initial_name: Test record
  updated_name: Updated test record
steps:
  - id: create
    do:
      include: shared.create_item
    with:
      item_name: {from_parameter: initial_name}
  - id: update
    do:
      request:
        method: PUT
        path: [items, {from_step: create, result: record_id}]
        body:
          name: {from_parameter: updated_name}
    expect:
      response:
        - check: success
        - check: field_equals
          field: itemId
          value: {from_step: create, result: record_id}
      backend_state:
        - check: span_exists
          span: item.update
  - id: read
    do:
      request:
        method: GET
        path: [items]
    expect:
      response:
        - check: success
        - check: collection_matching_count
          field: items
          matching:
            id: {from_step: create, result: record_id}
            name: {from_parameter: updated_name}
          count: 1
```

The unchanged parent sidecar pins the actual bytes of `shared/create_item.yaml`.
It is generated with a real digest in executable documentation tests, not with
a pretend approval hash. No schema version bump or second declaration format.

## 2. Exact declaration contract

- `results` is optional. If present it is a mapping (empty is allowed), with
  unique, non-blank string names. No name coercion or interpretation of `/` as
  nesting. Names are literal mapping keys.
- Each result has exactly `from_step` and `response_field`, both non-blank
  strings. The source must be an authored, local request-bearing step in the
  declaring Scenario. Any such local step may be named because this metadata
  is checked after all its steps load. Multiple names may reference one field,
  or fields from different local steps.
- A request-bearing UI step has a declared `expect.request`. Requestless UI,
  wait, unknown steps, include nodes, or expanded child leaves are not result
  sources. No re-export through another include, no recursive alias, no
  computation, literal result, expected-value extraction, or arbitrary code.
- A caller uses exactly `{from_step: <earlier include id>, result: <name>}`.
  It cannot address a future/current include, ordinary request step, unknown
  name, or undeclared output. `result` and `response_field` are mutually
  exclusive. Invalid reference-shaped objects are errors, not literal fallback.
  `result` alone is not a reference marker: an ordinary business object such as
  `{result: ok}` remains data. A named reference is recognized by `from_step`;
  existing `from_parameter` and `response_field` marker rules remain unchanged.
- Ordinary local `{from_step: <earlier request step>, response_field: <field>}`
  remains unchanged. Authored access to an expanded `include/inner` response is
  rejected; qualified IDs remain internal execution/report identities only.
  There is no compatibility escape hatch exposing undeclared child fields.
- Named references work in all existing value positions, including request
  segments/body, UI fill value, scalar assertion values, collection matching,
  and a later include's `with`. No new parameterized positions are introduced.
  Literal parameter values that resemble references must remain literal data.
- An include with no results is still useful for its steps and checks. Declaring
  results does not count as an assertion: standalone children must independently
  satisfy the existing effective-assertion rule.

## 3. Compilation, runtime, and failure semantics

The loader resolves result names into the existing `Binding`/`ValueRef` model,
scoping the source to the include invocation. No runtime return stack, shared
output store, new runner loop, projection, adapter method, or port is introduced.
Executable leaves are equivalent to an independently authored flat flow; source
and result-interface metadata are diagnostic and may differ.

Values come from actual normalized responses in the current run and projection,
not from an assertion, default parameter, cached earlier run, or another
projection. Frontend mock responses remain mock evidence. Separate invocations
of the same child do not share parameter or response values.

Every child step executes in order before a following parent step can consume a
result. FAILED/ERROR/SKIPPED within the child blocks subsequent leaves, including
the consumer, even if the named source step previously succeeded. A child result
is not an early return. Runtime execution is not transactional and adds no
rollback of already completed actions.

Result declarations are read-only source aliases, not extra assertions. Unused
aliases do not force response reads or turn absent fields into failures. When a
result is consumed, the existing binding rules apply: missing or null fields
cause ERROR before the consuming action; zero, false, and empty string survive.
The receiving position still enforces its current type constraints. Failure to
resolve one of several bindings remains atomic; no partial binding map leaks.

All declaration errors and pin mismatches occur before authentication or actions.
Renaming an internal source step and its result mapping leaves the caller YAML
unchanged, but changes child bytes and still requires an explicitly reviewed pin
update. Renaming/removing a public result requires caller review. Hashes prove
content agreement, not approval, and reused child review does not approve caller
arguments or whole-parent business goals.

## 4. Reports and review

Keep qualified leaf IDs and existing `source_lookup` and `localize()` behavior.
Explicit `validate --expand` shows the public result names and their symbolic
source mappings, as well as the verified flat execution plan. It must not run
adapters or include actual response values. Default validation stays concise.
Declaration literals are visible only under the existing explicit expansion
confidentiality warning; named results do not authorize runtime export.

No new default repr, serializer, report, or CLI output may publish resolved
values. Existing sensitive-binding/report boundaries remain. Diagnostic model
fields must be keyword-only and excluded from equality/default repr; the
explicit view can render their declaration-only content.

## 5. Required evidence and negative controls

1. Multiple results from one step and from different local request steps;
   omitted/empty results; standalone child and parent load.
2. Reject non-mapping results, duplicate/non-string/blank names, non-mapping or
   incomplete/extra-field result sources, non-string/blank source values,
   literal/expression/parameter-valued sources, unknown/requestless/include
   sources, alias/re-export chains, and a child with no effective assertions.
3. Reject unknown/missing result names, result on an ordinary step, forward/self
   include references, mixed `result`/`response_field`, and direct qualified
   child access (including `with` and collection matching).
4. All existing supported value positions preserve strict types and literal
   reference-shaped data. Later include arguments can use an earlier named
   result; standalone child references cannot reach parent environment.
5. Independently authored flat/include equality of executable models and backend
   reports; repeated includes and multiple outputs remain isolated. Internal
   step rename needs a new pin but no caller YAML change. A stale pin fails.
6. Real Demo backend + contract, frontend mocks, and live Chromium e2e use named
   results. Preserve one context/action sequence and qualified report/recording
   identities; no new adapter assumptions or private product evidence.
7. Child FAILED/ERROR/SKIPPED after an output source blocks consumers. Missing/null
   consumed values fail before action; unused absent output does not fail.
   Falsy values, bind atomic failure, and sensitive repr/diagnostic limits hold.
8. `validate --expand` exposes aliases and verified sources without execution;
   invalid declarations produce no partial plan. Maintained full YAML examples
   pass the real loader with exact child pins.
9. Preserve one-level/same-actor/pinning/limits tests and normal runtime
   regressions. No core import of adapters.
10. Preserve the original frozen fault harness and baseline/candidate JSON bytes.
    Add a separately named, explicitly migrated declaration fixture set using
    named results, reusing the exact fault injection/observations. Compare it
    with original independently authored flat controls and their frozen results.
    Do not rewrite old measurements or classify setup errors as detected faults.

An independent auditor must examine implementation, runtime counterexamples,
privacy, test strength, and the complete diff, not only rely on developer tests.
Acceptance requires full installed-environment tests (real browser, no skipped
required tests), isolated core-only tests, validate/expansion, lock, hygiene,
diff checks, and an explicit file scope. Hosted CI remains a later submission
gate. Passing synthetic tests does not prove reduced human review cost or
real-product adoption value.

## 6. Explicit exclusions

No multilevel inclusion, recursion, dynamic include target, actor switching,
expression language, conditionals, loops, output computation, re-exports,
runtime value serialization, authoring UI, private migration, or approval
automation. No changes to MANIFESTO, BRAND, or product code. Delivery is code,
tests, maintained public examples, SCENARIO contract, and a bounded acceptance
record; any further expression/semantic change requires maintainer confirmation.
