# Explicit request query parameters

## Authority, sources, and boundaries

The maintainer approved the complete five-step filter/next-page example and
authorized specification, development, independent audit, and architect
acceptance on 2026-10-17. Starting main is `eaca8cb`. Submission is not authorized.
Keep format 1, the existing do/expect structure, users/sessions, and one-level
inclusion. No private workspace is accessed or changed. Sources are the approved
neutral example and existing public Documents, Demo, core, and browser code.
Public artifacts are English; no private product details or local paths belong
in them. MANIFESTO, BRAND, CI, dependency changes, and product-specific features
are outside scope.

## Purpose and non-claims

Declare per-request filtering and pagination inputs rather than deriving them
from global parameters inside a resolver. Follow a response-derived cursor in
an explicit next step, and verify the query actually emitted by a browser.
No automatic pagination, expressions, loops, new assertion vocabulary, headers,
uploads, non-JSON bodies, repeated query keys, or nested query structures.
Synthetic results demonstrate bounded capability, not real-product adoption or
independent contract evidence.

## Frozen declaration and value rules

Optional `query` is a mapping in `do.request` and in the existing UI
`expect.request`. Keys are nonempty literal strings. Values are single strings,
integers, booleans, finite floats, or existing parameter/prior-response/named
result references resolving to those types. Empty strings, zero, and false are
values, not omissions. Null, lists, mappings, non-finite numbers, and dynamic
keys are rejected; known invalid values fail loading, runtime invalid response
references block the dependent action under the existing dependency policy.
No query reference is resolved by interpreting literal strings as code.

Serialization is deterministic: strings unchanged; integers decimal; booleans
`true`/`false`; finite floats use JSON numeric spelling. The observable HTTP
comparison is between decoded string keys and values: integer 1 and string
`"1"` have the same wire representation. This does not weaken type-strict body
or response assertions. Encode each key/value once with standard URL encoding;
key ordering is not semantic. Preserve blank values. Decode percent escapes
and plus-space encoding from real URLs; reject malformed encoding, invalid
UTF-8, or duplicate decoded keys instead of overwriting values. Bare wire keys
may represent empty strings. Percent-encoded delimiters remain data.

For UI checks, omitted query retains existing method/path/body-only scope;
explicit `query: {}` requires no parameters, and a nonempty mapping requires
exact equality, including no extra keys. For API commands, omitted/empty query
sends no query. Resolvers map routes, not query business values: they must
preserve the declared encoded meaning and cannot add, remove, or override
parameters. Request paths cannot carry a second embedded query or fragment.
Authentication stays in the session port, not query synthesis.

## Data and execution boundary

Use a shared product-neutral query utility for validation, serialization, URL
encoding and observed parsing. `RequestTemplate.query` retains declaration
values/references (None means omitted). `RequestSpec.query` carries decoded
wire strings in a new keyword-only mapping, defaulting to an independent empty
mapping, hidden from default repr and tagged sensitive. This is actual request
evidence, never a copy filled from an expectation. Optional mock-fixture query
uses the same wire representation; None preserves existing fixture scope,
while an explicit mapping constrains the ordered fixture. No mock data may be
generated from expectations.

Binding preparation is atomic, including query values. Inclusion rewriting,
named results, instantiated validation, expanded review and change-impact
inspection preserve and expose declared query references. Existing sensitive
runtime binding/report rules apply; error messages must not echo query values.
Polling reuses the prepared query and records every actual attempt. Sessions,
ordinary assertion continuation, explicit stop and missing dependencies retain
their accepted semantics.

Backend validates resolver ownership before sending, and compares returned
request evidence (including query) against the protected sent request. Recorder
and normalizer cannot rewrite it. Reference drivers encode query at transport
time without modifying the recorded mapping. Actual transport paths remain
adapter evidence, not a claim that a malicious driver is independently observed.

Browser support extracts query from the real fetch/XHR request URL before
routing/recording; logical path mapping receives only the path. Duplicate or
malformed API query is an execution error and must not be silently sent as a
valid supported request. Static document/resource queries are not new API
assertions and keep their existing transport scope. Existing origin, action,
user, session and request identity checks
remain. If one method/path-associated request exists, an unequal declared query
is an ordinary failed request check. If several exist, a declared query may
select exactly one exact query match; zero/multiple matches remain ambiguous
execution errors. Unassigned/background traffic cannot satisfy assertions.
Retain all actual query evidence and check traffic/response/Recorder equality.
Mock routing checks explicitly supplied fixture queries, not just path.

Contract remains response compatibility over verified backend recordings keyed
by step/method/template path, not a second sender or independent query witness.
Runtime query values do not become endpoint identities. Ensure query-only
bindings do not break response-contract evaluation or reference availability.

## Approved executable example

Add `examples/documents/scenarios/filter_and_next_page.yaml` with scenario ID
`documents.filter_and_next_page`, users `[editor]`, parameters category `guide`,
first_title `Getting started`, second_title `Advanced usage`. English comments
may translate the approved Chinese explanation; preserve expression and values.
Run against a fresh isolated public Documents target with creation-order lists.

1. `create_first`, stop: POST documents with parameter title/category; assert
   status 201, success, has document_id.
2. `create_other_category`, stop: POST documents with title `Internal memo`,
   category `memo`; assert 201, success, category equals memo.
3. `create_second`, stop: POST documents with parameter title/category; assert
   201, success, has document_id.
4. `first_page`, stop: GET documents/search with category parameter, limit 1,
   cursor 0; assert 200, success, returned 1, one collection member matching
   first creation ID/title/category, and next_cursor 1.
5. `next_page`: same route/filter/limit, cursor from first_page.next_cursor;
   assert 200, success, returned 1, one member matching second creation
   ID/title/category, and next_cursor null.

Preparation remains visible actions; environment isolation/disposal is the
test harness's responsibility. No reset or cleanup is hidden in the adapter.
Migrate maintained Documents search declarations to explicit query values and
remove resolver global-input/default synthesis. Do not weaken their assertions.
Preserve historical records rather than rewriting past evidence.

## Required tests and acceptance

1. Real loader: both request locations; omitted/empty, scalar values and existing
   references; reject malformed mappings/keys/values, extra syntax and known
   invalid include parameters. Preserve schema_version 1.
2. Binding/reference coverage: from_parameter/from_step/from_result, child
   expansion and review; missing/null/nonscalar dependency blocks before action,
   no partial bindings; zero/false/empty values survive.
3. Encoding round trips: Unicode, spaces/plus, ampersand, equals, percent, slash,
   blanks, ordering; malformed escape/UTF-8 and repeated decoded keys fail.
4. API: real Documents five-step example, backend+contract and explicit-API e2e;
   actual target receives correct values and returns distinct matching pages.
   Resolver additions/drops/changes, embedded query, and changed returned or
   Recorder query cannot pass. Poll attempts retain query. No extra contract send.
5. A second synthetic consumer using Demo/reference transport and real Chromium:
   browser live and mock read actual query; wrong/missing/extra values, explicit
   empty, omitted scope, same-path multiple requests, ambiguity, wrong-query
   mock fixture, background attribution, replay and paired evidence mutation.
   Negative controls must reach the query check rather than fail unrelated setup.
6. Sensitive sentinel values absent from default permit/traffic/report/query
   representations and failure details. Declaration expansion intentionally
   displays source values only under its existing review/confidentiality rules.
7. Full regression with real Chromium (no skip), isolated dev-only regression,
   maintained declarations and documentation samples, lock, hygiene, and diff
   checks. Independent reviewer runs additional probes and records findings.

Architect acceptance records actual commands, results, limits, and accepted
file scope. Keep all changes unstaged, uncommitted and unpushed; no private
workspace operations. Query filtering is product-neutral, needed by unrelated
document/catalog consumers, and addresses declaration/evidence capability, not
a product-specific behavior exception.
