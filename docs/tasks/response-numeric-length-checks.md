# Response numeric and list length checks

## Authorization and scope

The maintainer approved the complete filter/page-limit/next-page example,
`field_compare`, `collection_length`, and the failure rules below. Specification,
development, independent audit and architect acceptance are authorized, followed
by public submission after those gates. Keep `schema_version: 1`, the existing
structure, one-level inclusion, users/sessions and continuation policy.

Use only the approved neutral expression and existing public code. Public prose
and examples are English. Do not access or modify private workspaces, real
products, MANIFESTO, BRAND, dependencies or CI configuration.

## Purpose and non-goals

Express numeric limits on an observed normalized response field and bounds on
the actual length of an observed list. A reported count and a list length are
separate observations; neither is synthesized from an expectation. The checks
do not establish that those two values equal each other, database totals,
complete pagination, UI identity or real-product adoption.

No arithmetic, tolerance, numeric coercion, new reference shapes, strings/object
lengths, filtering inside length checks, automatic pagination, new actions,
deeper inclusion, generators, raw JSON paths or general schema engine. Existing
`field_equals`, `field_not_equals`, `collection_matching_count`, `count_gt` and
`span_attr` keep their exact behavior, including their current reference limits.

## Approved declaration

Both checks belong only to `expect.response` and require exactly `field`, `op`
and `value`. `field` is a nonblank literal top-level normalized field name;
punctuation remains literal. `op` is one of `>`, `>=`, `<`, `<=`, `==`.

```yaml
- check: field_compare
  field: returned
  op: ">="
  value: 1
- check: field_compare
  field: returned
  op: "<="
  value: {from_parameter: page_size}
- check: collection_length
  field: documents
  op: ">="
  value: 1
- check: collection_length
  field: documents
  op: "<="
  value: {from_parameter: page_size}
```

This fragment requires a declared positive integer `page_size`. Full executable
examples are required below. Thresholds accept existing literals, parameters,
earlier response references (including approved member selectors), and included
named results. Do not add same-step references or exported-result selectors.

For `field_compare`, both operands must be exact built-in integers or finite
floats. Booleans, null, numeric strings and containers are not numbers. Ordering
compares integer/float numeric values without converting arbitrary integers to
float or introducing rounding. Equality is type-strict: integer 1 and float 1.0
are unequal. Zero and negative numbers remain valid numeric operands.

For `collection_length`, the observed field must be a finite JSON-like list.
Count every element, including duplicates, nulls and valid heterogeneous members;
there is no matching predicate, sorting or item-type assertion. The threshold
must be an exact nonnegative integer, never a boolean or float, including 1.0.
Only an actual empty list has length zero. Lists are inspected without mutation.

Reject missing/extra parameters, unknown checks/operators, dynamic/blank field
names, malformed/forward/self references and known invalid thresholds. Validate
parameter defaults and instantiated include arguments at loading. Reject repeated
`(check, field, op)` constraints, even with different thresholds; distinct
operators coexist and all must be evaluated. Both checks imply presence and
conflict with `field_absent` on the same field. Do not introduce a general range
solver, deduplicate bounds silently, or change legacy constraint rules.

## Evidence and failure classification

| Condition | Execution result |
| --- | --- |
| Current field missing | FAILED, never substitute zero or an empty list |
| Present finite JSON-like value of the wrong type, including null | FAILED |
| Valid operands but comparison does not hold | FAILED |
| Invalid fixed or parameter threshold | DeclarationError before execution |
| Missing/null/invalid response-derived threshold | Local BLOCKED before action; no partial resolved bindings |
| Examined value has non-finite numbers, cycles, unsupported objects or invalid object keys | ERROR |
| Malformed normalizer port output or observation/execution error | Existing ERROR policy |

Validate only the examined field and expected operand; do not add whole-response
validation that rejects unrelated opaque fields. For examined containers validate
their finite JSON-like contents before reporting wrong type or taking length,
including nested invalid data. These rules must not depend on comparison
short-circuiting or whether a threshold would trivially succeed.

Resolve response-derived thresholds and validate their use sites in shared step
preparation, before authentication/action, retaining existing atomic binding and
snapshot guarantees. A failed source assertion can still supply an available
response under continuation. An unusable reference blocks the consumer, not an
independent step; execution ERROR/SKIPPED and explicit `on_failure: stop` preserve
their existing stopping behavior. Successful and failed checks participate in
the normal report aggregation; strict admission still requires PASSED.

Default diagnostic and report representations must not expose numeric thresholds,
actual values, raw members or synthetic sensitive sentinels. Name the check,
field, operator and structural reason. Do not change existing scalar diagnostic
behavior or claim generic serialization is safe.

## Shared execution and contract

Use one bounded evaluator and operand validation for backend, API e2e, actual UI
e2e, frontend mock responses, polling attempts and offline contract comparison.
Do not add a second orchestration loop or alter ports. Mock evidence remains
distinct from live responses. Polling continues to evaluate its actual attempts
and final/timeout rules without new syntax or timing policy.

Contract stores every numeric/length constraint in order, not a single bound per
field. Compare against actual provider normalized values, and derive referenced
thresholds from actual provider source recordings, never declaration expected
values or backend diagnostic bindings. Missing current fields and valid wrong
types are mismatches; invalid examined data or unavailable/invalid referenced
thresholds produce contract ERROR under its existing aggregate error boundary.
Contract has no action to block and sends no requests. It is not independent
evidence. Protect new constraint value fields from default repr.

Preserve selectors, include parameter substitution, named results, expanded
review and impact inspection. New response expectations do not alter UI/request
checks, actor/session selection, inclusion depth, or result-interface grammar.

## Approved example and independent consumers

Add `examples/documents/scenarios/check_page_limits.yaml`, scenario
`documents.check_page_limits`, with English presentation of the approved example:
users `[editor]`, category `guide`, page_size 1, first/second title parameters.
Use an empty isolated Documents target with existing creation-order behavior.

1. POST the first guide, check 201/success/document_id, stop on failure.
2. POST one memo, check 201/success/category memo, stop on failure.
3. POST the second guide, check 201/success/document_id, stop on failure.
4. GET documents/search with declared category/limit/cursor 0. Check 200/success;
   returned >= 1 and <= page_size; documents length >= 1 and <= page_size;
   exactly one member matching the first actual ID/title/category; next_cursor
   not equal to null. Stop on failure.
5. GET the next page with the actual prior next_cursor. Repeat bounds, check the
   second actual ID/title/category and terminal next_cursor equal to null.

The expected two pages depend on the fixed setup and page size; do not silently
generalize the example to arbitrary parameters. Preparation stays visible; the
adapter does not seed, filter using assertions or invent evidence. Retain the
existing Documents target/normalizer where possible. Its derived reported count
is not an independent witness. Add a separate synthetic Records consumer whose
reported count can disagree with its actual list, plus real Chromium live/mock
controls. New examples must run, not merely load.

## Verification requirements

- Declaration shape, every operator and strict boundary neighbors; invalid
  fields/operators/thresholds, duplicate and absence conflicts, unchanged syntax.
- Integer/float ordering and strict equality, huge integers, negative/zero,
  bool/int and string/number distinctions, empty lists and duplicate/mixed items.
- Missing/null/wrong-type observations versus non-finite/cyclic/unsupported data;
  malformed data cannot pass even against a trivially permissive threshold.
- Parameters, prior response/member/result thresholds, include substitutions,
  invalid defaults/overrides, no action/authentication or partial bindings when
  dependencies block, valid independent continuation and explicit stop.
- Complete range constraints in contract, actual provider thresholds, missing
  evidence, source mutation and protected snapshots, no data in default repr.
- Backend/API e2e/frontend mock/live UI, polling success and FAIL/SKIP timeout,
  no change to execution provenance, user/session and one-level constraints.
- Execute the approved five-step example and independent Records consumer.
  Fault controls: false reported count, oversized/empty actual page, ignored
  filter, repeated first page, unavailable cursor, wrong response types.
- Full suite with real Chromium and no browser skips, fresh dev-only suite,
  documentation/example validation and expansion, product-agnostic litmus,
  lock/hygiene/diff checks, public source review, independent audit and acceptance.

The capability is product-neutral, useful for independent documents and records,
and expresses declared numeric/list obligations rather than compensating for a
product-specific response behavior. Broader correctness and maintenance savings
remain separate questions.
