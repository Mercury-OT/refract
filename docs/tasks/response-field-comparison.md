# Complete response-field equality and inequality

## Authorization and scope

The maintainer approved the four-step records example, complete object/list
comparison through `field_equals`, and the new `field_not_equals` check. Keep
`schema_version: 1`, the current declaration structure, references, users,
sessions, one-level inclusion, named results and failure-continuation policy.
Specification, implementation, independent audit and architect acceptance are
authorized; public submission is authorized only after these gates pass.

Sources are the approved neutral example and existing public code and examples.
All public prose is English. Do not access the private workspace or introduce
private product information, paths, evidence or measurements. MANIFESTO, BRAND,
dependencies and CI configuration are outside scope.

## Purpose and limits

Compare the complete value of one observed normalized response field with a
literal, parameter, prior response field or included named result. This closes
the object/list and explicit-inequality gaps without duplicating the existing
scalar equality spelling. A successful comparison concerns that selected field,
not an entire raw response, all database state, hidden fields or independent
authorization-decision evidence. Two equal error payloads are not evidence of
successful business behavior: the approved example retains success/status/ID
controls on both reads.

No whole-HTTP-response comparison, exclusions, JSONPath, approximate matching,
unordered-list matching, arithmetic, coercion, deeper inclusion, new action or
reference syntax, generators, UI authoring, or real-product changes.

## Declaration

Both checks belong only in the existing `expect.response` list, with exactly
`field` and `value` parameters. `field` is a nonempty literal normalized field
name. Retain `field_equals`; add `field_not_equals` without a `same_as` alias.

```yaml
- check: field_equals
  field: content
  value: {from_step: read_before, response_field: content}
- check: field_not_equals
  field: content
  value: {from_parameter: attempted_content}
```

Only these response checks gain object/list expected values. Other assertion
value/ID positions, collection matching predicates, path/query/header values
and span operations keep their current domains. Literal expected values and
parameters must be finite JSON-like data: null, exact booleans, integers, finite
floats, strings, lists, or string-keyed objects recursively containing such data.
Retain the existing data/reference parsing rules, including nested references
where already supported. Runtime response data resembling reference syntax is
data, never reparsed as executable references.

Unknown/extra parameters, empty/invalid field names, duplicate same-check
constraints on a field, and `field_absent` combined with either comparator on
that field are invalid. One equality and one inequality on the same field are
allowed and independently evaluated; no symbolic contradiction solver is added.
The new presence-requiring term must participate in applicable loader/include
validation and review/expansion logic without bypassing existing checks.

## Comparison and evidence

Use one shared, type-strict recursive comparison. Object keys and values must
match completely; key order is immaterial and extra keys make values unequal.
Lists require equal length, element order and recursively equal elements.
Boolean/integer, integer/float, number/string and object/list types are distinct.
An empty object/list is a real value. Null inside a literal or object/list is
ordinary data, distinct from a missing field. No normalization, stringification,
sorting, trimming, numeric tolerance or subset comparison is introduced.

Both checks require the current field to exist. Missing current fields fail
either check; missing must never satisfy inequality. Present, valid unequal
values fail equality and pass inequality. Present, valid equal values pass
equality and fail inequality. Invalid observed data (non-finite values, cycles,
non-string object keys or unsupported runtime objects) is an execution error,
not inequality evidence, even when its type already differs from the expected
value. Known invalid declared values fail loading. Invalid response-derived
expected values block the consumer before its action under the existing rule.

Preserve current dependency semantics: missing source steps/fields and top-level
null response references are unavailable and block the consuming step atomically.
Do not broaden null-reference semantics in this task. A source assertion failure
does not discard an otherwise available response. Ordinary comparison failures
continue by default; explicit stop, execution errors, polling timeout and strict
run-status rules remain unchanged.

Core must retain stable observations: a normalizer reusing a mutable result
buffer, or a later callback mutating a received container, must not rewrite a
previous observation/expected baseline and manufacture equality. Isolate retained
normalized evidence and response-derived container inputs at their ownership
boundaries. Preserve the documented shallow top-level `resolved_bindings`
diagnostic semantics within the run; this is not a generic immutability system
or protection against a consistently dishonest adapter. Do not require unrelated
fields to adopt a new assertion-specific validation domain merely to run an old
declaration.

## Projections, contract and confidentiality

Backend, explicit-API e2e, frontend mock responses and live UI responses reuse
the response evaluator. Polling evaluates each actual attempt with unchanged
final-response and timeout behavior. Contract must preserve and evaluate every
comparison, including multiple types on one field and references, against
actual backend recordings; it must not reduce inequality to field presence or
silently overwrite constraints. Contract makes no additional request and does
not become independent evidence. Missing/invalid provider or reference evidence
must never produce a passing contract result.

New comparison diagnostics must not print entire containers or sensitive values.
Use field names, check names and bounded reason labels. Do not leak nested keys
or contents through generic repr, mismatch records, default reports or error
messages. Keep any necessary raw values in sensitive repr-hidden fields. Preserve
legacy scalar-equality diagnostic behavior where it does not disclose container
values; inequality diagnostics are value-free. Generic serialization and
unobserved arbitrary callback exceptions are not claimed safe by this slice.

## Approved example and independent consumers

Publish `examples/minimal/rejected_update_preserves_content.yaml`, retaining the
approved `records.rejected_update_preserves_content` ID and English comments.
Users are `[creator, peer]`. Parameters are:

- `original_content`: title `Original record`, status `draft`, tags
  `[review, shared]`.
- `attempted_content`: title `Unexpected change`, status `published`, tags
  `[edited]`.

Preserve the four approved steps and obligations:

1. `create`, creator, explicit stop: POST records with body.content from the
   original parameter; status 201, success, has id.
2. `read_before`, creator, explicit stop: GET records/create.id; status 200,
   success, returned id equals create.id, content equals original parameter.
3. `peer_attempts_update`, peer, default continuation: PATCH that same id with
   attempted content; status 403, failure, error_code equals `owner_required`.
4. `read_after`, creator, default continuation: GET that same id; status 200,
   success, id equals create.id, content equals read_before.content and differs
   from attempted content.

The final inequality is a complementary example; equality to the first observed
content is the unchanged-content obligation. Execute this exact declaration
against a neutral synthetic target that does not inspect Scenario expectations.
Also validate a distinct consumer using the existing enveloped Documents target
and adapter. Extend only its public synthetic behavior and truthful normalization
as needed. No adapter may hide preparation, synthesize expected values or discard
parts of the selected object. Add independent target-state/request observations
and a deliberately faulty rejection that really changes content while returning
403; it must be detected by the unchanged final read. Keep rejection reason and
database/production-adoption claims bounded.

## Required verification and acceptance

1. Loader and preparation: both terms, literals/parameters/prior responses/named
   results, nested references, empty/null data, object/list values, extra/unknown
   keys, duplicate/absence conflicts, non-finite/unsupported values, no widening
   of unrelated assertion or transport positions.
2. Strict comparison: complete nested keys, added/removed/changed members, list
   length/order, bool/int and int/float distinctions, missing versus null/empty,
   valid mixed types, malformed/cyclic observed values and invalid dependencies.
3. Backend, frontend/e2e response paths, polling, continuation/stop, sessions,
   one-level inclusion/named-result wiring, atomic unavailable-source blocking,
   complete sensitive bindings and stable snapshots under later mutation.
4. Contract preserves both same-field terms and all declared obligations;
   literal/reference/container comparisons agree with runtime. Missing, null
   source, malformed provider, reordered/duplicate recording and tampering
   controls retain existing evidence boundaries; report and mismatch repr do
   not disclose container sentinels.
5. Exact approved records example and independent Documents consumer run through
   backend+contract and explicit-API e2e. Negative controls cover unauthorized
   modification despite refusal, equal error bodies, wrong object, missing data,
   unchanged inequality target, legitimate differing content, and invalid user
   or response reason. A weak variant can demonstrate the missing comparison
   without weakening the maintained example.
6. Real Chromium shared-evaluator coverage for mock/live response objects/lists;
   no expectation injection or browser-helper changes unless a specific defect
   requires them. Existing full browser suite remains mandatory.
7. Full regression, isolated dev-only suite, maintained declarations and YAML
   documentation loading, lock, repository hygiene including additions, diff
   checks, independent audit and architect acceptance. Record actual results,
   limits and exact accepted file scope before public submission.

The capability is describable without product terms, serves unrelated records
and document workflows, and repairs an expression/evidence gap rather than
special-casing a product. Synthetic success is not proof of adoption value.
