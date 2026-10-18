# Bounded response member references

## Authorization and scope

The maintainer approved dictionary `key` references and unique list-member
references using `matching` plus `member_field`, including their unavailable-value
rules. Specification, development, independent audit and architect acceptance are
authorized, followed by public submission after those gates pass. Keep
`schema_version: 1`, the existing structure, users, sessions, one-level inclusion,
named results, projection boundaries and failure-continuation policy.

Sources are the approved neutral examples and existing public code. Public prose
and maintained examples use English. Do not access or change private workspaces.
Do not introduce private names, paths, evidence or measurements. MANIFESTO, BRAND,
dependencies, CI configuration and real products are outside scope.

## Purpose and limits

Read an already observed normalized dictionary member, or exactly one matching
member of an observed normalized collection, without adding scenario-specific
flattening or first-item selection to an adapter. Stable existing normalization
aliases remain valid; no adapter migration is required merely to use old syntax.
This does not expose raw response paths, fetch additional pages, prove database
uniqueness, infer UI identity, or establish adoption or maintenance savings.

No dynamic keys, recursive selection, path expressions, JSONPath, array indexes,
fallback values, arithmetic, generators, new actions, deeper inclusion, or new
named-result interface. New selectors apply only to local response references;
`results` definitions and `{from_step, result}` retain their existing exact shape.
Included children may use selectors internally, and callers may pass selected
values through the existing `with` parameter mechanism.

## Declaration

Exactly three local response-reference shapes are permitted:

```yaml
# Existing whole-field reference.
{from_step: create, response_field: record}
```

```yaml
# One literal dictionary key.
{from_step: create, response_field: record, key: id}
```

```yaml
# Exactly one matching list member, followed by one literal member field.
from_step: locate
response_field: records
matching:
  code: {from_parameter: record_code}
member_field: id
```

These are illustrative values. Maintained full examples and individual
documentation fragments must be checked as their proper declaration/value contexts.

`response_field` always names a top-level normalized field on an earlier local
request-bearing step. `key` and `member_field` must be nonblank literal strings.
Punctuation such as dots and slashes is part of the literal name, never a path.
Selector fields are mutually exclusive: reject `key` with `matching` or
`member_field`; reject either list-selector field without the other. Reject
unknown keys, dynamic/empty/non-string keys, missing sources, forward/self
references, selector fields on parameter/result references and results definitions.
Do not interpret ordinary response dictionaries or literal parameter data as
reference declarations.

`matching` is a nonempty string-keyed mapping using the existing collection
predicate domain: finite scalar literals, parameter values, plain earlier
response-field references or included named-result references. Match all keys on
the same member with the existing strict equality: false is not zero, true is
not one, and integers differ from floats. Literal/parameter null can match a
present null; a missing member key is not null. Do not recursively compose new
selectors inside these predicates. Known nonscalar predicates fail loading;
unavailable or nonscalar response-derived predicates block the consumer.

New references work wherever existing response references are supported, subject
to that position's unchanged type rules: action values, path segments, query and
header values, body values, supported assertion values and include parameters.
They do not become assertions or grant a new expectation domain.

## Runtime evidence and failure rules

Use the current projection's retained normalized response snapshot. Dictionary
selection requires a string-keyed dictionary and an existing literal key. List
selection requires a list of string-keyed dictionaries; any malformed member is
unavailable evidence, not an item to skip. Count all actual matching members,
including duplicates. Exactly one must match before the requested member field
is read. There is no first-item fallback and no implicit sorting or filtering.

Selected values must belong to the existing finite JSON-like response-value
domain. Containers may be used whole at allowed positions, but selection cannot
continue into them. Preserve existing invalid-data validation and snapshot
ownership without imposing a new restriction on unrelated normalized fields.
Selected runtime dictionaries that resemble references remain data.

Missing source/field/key, wrong selected container shape, zero/multiple matches,
missing member field, selected null or an invalid selected/use-site value cause
atomic local `BLOCKED` before the consuming action. Do not authenticate, invoke
the action or publish partially resolved bindings for that blocked step. Retain
the existing distinction from malformed normalizer port output or unrelated
execution errors. Independent steps may still execute under the current policy.
A failed source assertion alone does not erase its usable response. Explicit
stop, ERROR and SKIPPED retain their existing stopping rules.

Zero, false and empty strings remain actual values where permitted. A path may
contain integer zero but not false or an empty string. Do not coerce values or
turn absence into null. Selection independently enforces uniqueness even if a
preceding collection-count assertion was omitted or failed under continuation.
No new network request or polling attempt is performed to resolve a reference.
Existing polling retains its final actual response as the source.

Reading does not mutate evidence. Mutable selected values passed to consumers
must be isolated from retained snapshots. New diagnostics and repr must not dump
matching values, members, selected containers or sensitive sentinels. Existing
scalar assertion reporting is not a new general redaction promise; generic
serialization remains outside this task.

## Integration and review

Distinct references to a whole field, different dictionary keys or different
list predicates/fields must not alias internally, including punctuation and
strictly distinct literal types. Internal identities must not embed matching
values into request templates, report keys or default repr. Resolve predicate
dependencies deterministically before selection without exposing intermediate
partial bindings.

One-level include rewriting must preserve the selector, substitute child
parameters and earlier response dependencies correctly, and isolate separate
invocations. Existing named-result aliases and caller privacy stay unchanged.
The expanded review view and impact inspection must retain selector meaning,
including an unused `with` value; do not silently render a selector as a whole
field. Explicit review output remains source-confidential, not a safe runtime
report serialization format.

Backend, explicit-API e2e, frontend mock and live UI execution reuse the same
reference resolution. No new orchestration loop or adapter port is needed.
Contract resolves actual provider evidence with the same selection semantics,
including predicate dependencies and includes; absent/ambiguous evidence must
never yield a pass. It sends no requests and is not independent evidence.

## Examples and independent consumers

Publish the approved four-step Records flow in
`examples/minimal/create_locate_update_read.yaml`: create without an ID, query
the records list by a supplied immutable code, assert exactly one matching
record, PATCH the selected ID, then GET the ID returned and checked by PATCH.
Keep status/success checks and explicit stops on the first three steps. Check
the update's ID against the selected ID, code against the supplied code and
name against the new name; the final read checks the same three fields. English
names/comments are presentation translations of the approved neutral example.

Add a separate minimal dictionary example that creates an enveloped `record`
and reads its `id` through `key`. Use an isolated synthetic target with the
supplied code initially unused; this task does not generate uniqueness or add a
precondition field. No expected assertions enter target behavior or normalization.

Exercise both forms against independently implemented Records and Documents
consumers, reusing the existing public Documents adapter/target where suitable.
Retain complete observed objects/lists in normalization. A target not in first
position, shuffled rows, a duplicate match, wrong selected ID and missing data
must distinguish correct observations from fabricated or ambiguous evidence.
Use backend+contract and explicit-API e2e, plus real Chromium mock/live controls
for shared runtime resolution. Browser support code need not change.

## Verification and acceptance

1. Strict declaration shapes and all negative cases above; existing syntax,
   results, duplicate-key rejection and schema version remain unchanged.
2. Whole/key/list references coexist without collisions; all legal value
   positions, multiple predicates, plain response/parameter predicate sources,
   strict types, literal punctuation, null/falsy values and invalid use sites.
3. Zero/duplicate matches, malformed rows, missing source/key/field, non-finite,
   cyclic or unsupported selected data, independent continuation and explicit
   stop. No blocked action or partial resolved mapping.
4. Snapshot and callback mutation controls, runtime reference-looking data,
   same-run versus separate-run evidence, repr and diagnostic sentinels.
5. Internal child selection, parameter/response substitution through `with`,
   two child invocations, unused `with` review, unchanged named results, expanded
   review and impact rendering. No deeper inclusion or hidden child access.
6. Actual-provider contract checks, multiple predicate dependencies, missing or
   ambiguous provider evidence, polling final response and all response paths.
7. Approved Records flow, dictionary example, independent Documents behavior and
   genuine negative controls; real Chromium live/mock selection without skips.
8. Full regression, fresh dev-only regression, maintained Scenario/documentation
   loading, CLI expanded review, lock, repository hygiene including new files,
   diff/index checks, independent audit and architect acceptance. Record actual
   results and exact accepted file scope before public submission.

The capability needs no product terminology, serves unrelated records and
documents, and fills a data-reference gap rather than changing product behavior.
