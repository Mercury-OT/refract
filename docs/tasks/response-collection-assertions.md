# Bounded response collection assertions

Priority and delivery state are maintained in the [roadmap](../roadmap.md).
This specification uses approved product-neutral requirements, public code,
and synthetic fixtures. It does not incorporate private product evidence.

## Approved expression and scope

Keep the action-oriented Scenario format, metadata, steps, references, and
projection selection unchanged. Add exactly one response assertion:

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
`record_name` parameter. It checks the observed response collection, not UI
object identity, database state, all pages, or a separate hidden request.

No new schema version, expression engine, JSONPath, nested field traversal,
pagination executor, general schema validator, authoring UI, or product-specific
mapping belongs in this task. Existing historical evidence is not migrated.

## Declaration and matching contract

- Required parameters are exactly `field`, `matching`, and `count`; unknown
  parameters are errors. `field` is a nonempty string naming one top-level
  `NormalizedResponse.fields` entry, not a path expression.
- `matching` is a nonempty mapping of nonempty string field names to finite
  JSON scalar literals or the existing parameter/prior-response references.
  Lists and objects are not matching values. Duplicate YAML keys remain errors.
- `count` is a nonnegative integer; booleans and floats are invalid. It is not
  an expression or reference. Matching values, not matching keys, can reference
  parameters or earlier request-bearing steps.
- Validate known parameter values as scalars when loading. If a runtime
  prior-response reference resolves to a list or object, fail preparation with
  `ERROR` before the action; do not interpret it as a nonmatch. Preserve existing
  atomic reference resolution, missing/null response errors, and valid falsy
  response values. Literal null and a null parameter remain valid expectations.
- A member matches only when ALL named fields are present on that SAME object
  and are type-strictly equal to their resolved expected values. Extra fields
  are allowed. A missing field does not match even if the expected value is null.
  `false` is not `0`, `true` is not `1`, and string IDs are not numeric IDs.
- Ignore list order; count duplicate matching members separately. The check
  passes only when the observed number of matches equals `count`.
- An empty list can satisfy zero. A missing collection, a non-list collection,
  or ANY non-object list member fails the check, even for zero. Do not discard
  malformed members or turn missing evidence into an empty list.
- Multiple constraints on the same collection are allowed and ALL must be
  evaluated, including identical constraints. Do not overwrite them by field.
  `field_absent` on the same collection is a declaration conflict, even for
  count zero. Coexisting `has` is allowed.

Malformed observed collections produce a failed assertion, not a new report
status. Normalizer exceptions and reference-resolution errors keep their
existing ERROR semantics. Do not change existing scalar assertion behavior.

## Execution and contract

Backend, frontend mock response checks, and e2e response checks reuse the same
bounded evaluator. Polling uses this predicate under the existing timing,
terminal-recording, and FAIL/SKIP rules; it does not introduce list pagination.
Frontend evidence remains mock evidence, not live backend verification.

Contract must retain every collection constraint and check the final provider
recording's normalized collection with the same matching semantics. Resolve
prior-step expectations from actual provider response values and retain the
existing endpoint identity. Missing/invalid references cannot pass. Non-final
poll recordings must not satisfy a consumer requirement. Contract sends no
requests and must not silently reduce the new check to field presence.

Reuse a common evaluator rather than copying subtly different matching loops.
Do not mutate input collections, scenario assertions, or recordings. Any new
contract dataclass fields have independent defaults and are keyword-only;
fields retaining matching values must be hidden from default repr.

## Evidence and sensitive values

The adapter supplies the complete collection actually observed in that response
or page, with mechanical field mapping only. It must not use the Scenario's
expected values to filter members, select the first successful match, discard
malformed evidence, or manufacture a pass flag. Absence and malformed input
remain distinguishable. No claim of all-page completeness is made.

New diagnostics may name the collection and matching keys, expected/actual
counts, and a structural failure reason. They must not print matching values,
raw members, or entire collections, including in contract mismatch repr and
`localize()` output. Generic serializers remain sensitive; this is not a general
redaction system or protection from a malicious normalizer.

## Reference adapter slice

Update the public synthetic documents normalizer to expose a normalized
`documents` collection. Remove its first-item scalar shortcut for result sets;
retain unrelated receipt/document behavior and pagination metadata. Migrate the
maintained list Scenario to the approved assertion. Include a list with an
unrelated member before the target so first-item selection cannot satisfy the
test. Show a negative control that changes the target member while leaving an
unrelated member valid. Do not hide preparation in the adapter.

## Acceptance evidence

1. Vocabulary and loader tests cover required/unknown parameters, matching map
   shape, nonempty names, scalar limits, strict count types, duplicate YAML keys,
   existing reference validation, absence conflicts, and multiple same-field
   constraints.
2. Pure matching tests cover reordered lists, a target after a nonmatching
   member, conjunction on the same member, duplicates, false/zero, true/one,
   string/numeric IDs, missing/null, empty-list zero, and malformed evidence
   (including a valid match followed by a malformed member).
3. Parameter/prior-response tests exercise actual runtime substitution, falsy
   values, missing/null source fields, nonscalar reference errors before the
   action, atomic diagnostics, and fail-fast behavior.
4. Projection tests exercise backend, frontend mock, e2e, and polling terminal
   success plus FAIL/SKIP timeout with the new predicate; retain honest scope.
5. Contract tests prove it evaluates contents rather than presence, retains
   multiple constraints, handles references, uses only final recordings, and
   rejects malformed/changed provider evidence without modifying recordings.
6. Sensitive sentinels never enter the new check details, localize output,
   contract mismatch repr, or default report repr; no raw list is dumped.
7. The documents example runs backend plus contract with truthful full-list
   mapping, target-not-first coverage, and a real input mutation negative control.
8. Full regression with the real Chromium tests, declaration validation,
   dependency lock check, repository hygiene, diff/cached-diff checks, and an
   isolated core-only installation pass. Review public information sources and
   preserve non-public material and all unrelated files.

The maintainer has authorized submission after development, independent audit,
and architect acceptance. That does not waive the task branch, PR, required CI,
post-merge CI, and cleanup gates. No private repository submission is authorized.
