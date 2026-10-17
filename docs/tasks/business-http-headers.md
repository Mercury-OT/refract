# Business request headers and bounded response-header checks

## Authorization and scope

The maintainer approved the complete three-step idempotency example, optional
`do.request.headers` and UI `expect.request.headers`, `header_equals` and
`header_absent`, case-insensitive names, exact string values, and the rule that
unavailable evidence cannot prove absence. Development, independent audit and
architect acceptance are authorized. Submission is authorized only after those
gates pass. Keep format 1, the existing overall declaration, user/session rules,
one-level inclusion, named results and assertion-continuation semantics.

Sources are the approved neutral example and existing public core, browser,
Demo and Documents code. Do not access the private workspace. Public artifacts
are English. No private source, identifier, evidence, measurement or path may be
introduced. MANIFESTO, BRAND, CI and dependencies are outside this task.

## Purpose and exclusions

Declare business headers such as an idempotency key, verify the actual API or
browser request, and check selected response headers without normalizing them
into invented response fields. The example demonstrates one synthetic service's
retry contract, not universal HTTP idempotency behavior, database integrity,
concurrent retries, production adoption, or an independent contract observer.

No response-header references, dynamic ETag flow, multi-valued header language,
non-JSON bodies, uploads, raw attack traffic, new users or nesting semantics,
automatic unique values, concatenation, expressions, or implicit preparation.

## Declaration contract

`headers` is an optional mapping in both existing request locations. Names are
nonempty literal ASCII HTTP token names, compared case-insensitively. Duplicate
case-folded names are invalid. Values are literal strings or existing parameter,
prior-response or included-result references resolving to strings. No coercion
of numbers, booleans, null, lists or mappings. This bounded sender supports empty
or visible ASCII values with internal spaces; leading/trailing whitespace,
control characters and non-ASCII values are rejected rather than normalized.
Known invalid values fail loading; invalid runtime response references block
their consumers before sending under the existing dependency policy.

Omitted or empty headers add no business-header requirement. For UI observations,
declared entries are a subset: browser automatic or other undeclared headers do
not fail an otherwise matching request. Only declared entries are compared.
For API actions the resolver must preserve the complete declared business map,
case-insensitively, with no added, removed or changed values.

Credentials and transport controls are not business headers. Reject declarations
of Authorization, Proxy-Authorization, Cookie, Set-Cookie, Host, Content-Length,
Content-Type, Transfer-Encoding, Connection, TE, Trailer, Upgrade, Expect,
Accept-Encoding, Origin, Referer, User-Agent, Traceparent and Tracestate, plus
the `proxy-`, `sec-` and `x-refract-` prefixes, case-insensitively. Adapters must
also reject collisions with their product-neutral session credential header
names before sending; do not silently prefer either value. Authentication and
trace attribution retain their existing owners. A browser observation must not
use a credential header as declared business evidence merely because the
adapter uses a custom credential name.

Response assertions are:

```yaml
- check: header_equals
  header: Cache-Control
  value: "no-store"
- check: header_absent
  header: X-Internal-Debug
```

`header` is a literal token name; `value` follows the same string/reference rule.
Duplicate constraints on one case-folded name and contradictory equals/absent
constraints fail loading. Header names are not normalized response-field names.
An absent equals target or unequal observed value is FAILED. A present absent
target fails even if its value is empty. No comma splitting, whitespace trimming,
case folding of values or semantic Cache-Control interpretation is introduced.

## Evidence and minimal internal data changes

Add keyword-only sensitive, repr-hidden `RequestTemplate.headers` (None means
omitted) and `RequestSpec.headers` (independent empty default business mapping).
Add keyword-only sensitive, repr-hidden `RecordedResponse.request_header_items`
and `RecordedResponse.header_items`, each a complete ordered list of string
name/value pairs or None. None means unavailable, never an empty header block;
an explicit empty list means the complete observed block is empty. Retain the
legacy response headers mapping but hide it from default repr as well.

The raw pair lists are authoritative for new checks. A flattened dictionary
cannot prove uniqueness or completeness. Retain duplicates; an asserted name
with multiple occurrences is unsupported evidence and causes ERROR, even for
absence checks. Unrelated repeated names do not invalidate a single-valued
assertion. Missing/malformed complete evidence causes ERROR, not PASSED or an
ordinary business mismatch. Existing header-free declarations do not require
new evidence from older port implementations.

Completeness is relative to the identified observation boundary, not packet
capture. API drivers capture their built/sent request object or exact target
invocation. Browser support captures all headers exposed by the full browser
request API and the effective core trace/private-marker rewrite. Its forwarding
transport can additionally generate owned headers such as Host, Connection,
Content-Length and Accept-Encoding. Do not invent those values or claim to
observe every forwarded byte. They are excluded from business declarations;
independent peer tests verify that declared business values reach the target.
Response absence assertions require the complete provider response block (or
actual fulfilled browser response in mock mode), not a filtered list.

API request pairing still protects all RequestSpec fields. New raw request
evidence is recorded on RecordedResponse, not prefilled by a resolver. When a
business header is declared, compare it with the actual captured request block;
a valid wrong/missing value is a failed request check, while unavailable or
ambiguous evidence is an execution error. Preserve the actual response and
ordinary failure continuation so later observations can still run. Reference
drivers obtain evidence from the built/sent HTTP request or the exact in-process
target invocation, not by copying the Scenario expectation into an observation.

Capture response header evidence before invoking the normalizer. The normalizer
cannot supply, erase, rewrite or replace header evidence. Recorder boundaries
protect both raw blocks and request business maps. Report and diagnostic default
representations, exceptions, mismatch details and contract shapes must not echo
header values or credentials. This is bounded sensitive handling, not permission
for generic serialization or a claim of general-purpose redaction.

## Browser and mock behavior

Read the browser's complete actual request headers, not the reduced request
header dictionary. Keep the existing action/user/session/trace association and
forwarding controls; do not replace application business headers from Scenario
expectations. Collect the full response pair list before disposing the response.
Do not filter credentials and then claim that a filtered block is complete.
The capture/forwarding boundary above does not claim independently observed
transport-generated headers or automatic transport authentication. Credentials
visible in the captured browser block are retained sensitively, not inferred.

If one associated method/path request exists, its wrong business header produces
FAILED. If several exist, the existing explicit query constraint and then the
declared business headers may select exactly one; zero/multiple candidates are
ERROR. Unavailable header evidence cannot be silently discarded during selection.
Background or replayed traffic cannot satisfy assertions.

Add optional sensitive repr-hidden `MockResponse.request_headers` and
`MockResponse.response_headers` mappings. They are explicit independent fixtures,
never generated from expectations. Request fixture entries constrain only those
names. Response fixture entries define supplied response headers in addition to
the existing JSON transport default; omission retains existing fixture behavior.
Actual recorded mock blocks must agree with the fixture for supplied names and
retain completeness, including transport-generated headers such as Content-Length.
Collect the fulfilled browser response rather than labeling the bare fixture
mapping a complete observation. Core consumption checks must detect header tampering, not
only compare JSON bodies. Frontend remains mock evidence, never live proof.

## References, projections and contract

Bindings resolve atomically across headers, body, path, query and expectations.
Include rewriting, instantiated-value checks, expanded review and impact
inspection preserve header references and the existing confidentiality policy.
Polling preserves the prepared business headers on every attempt and evaluates
response-header assertions against each actual attempt. Retain every attempt's
request-header checks. A response-readiness timeout with SKIP still skips the
step and blocks subsequent execution, but cannot erase an already failed request
check: domain and run aggregation must report FAILED whenever any performed check
is false. A response-only SKIP without such a failed request check remains
DEGRADED. Existing result/status,
users, anonymous isolation, continuation and explicit stop rules remain.

Backend and explicit-API e2e verify actual request evidence. Frontend and UI e2e
check associated actual browser headers. Response checks share one implementation
across these paths. Contract retains response header constraints and evaluates
the same protected backend recordings, including string references and missing
evidence. Its endpoint identity remains step/method/template path: headers do
not create identities. It sends no request and is not independent evidence.

## Executable public examples

Preserve the approved `records.idempotent_create` three-step declaration in an
English-commented example: creator; fixed key `record-create-example-001` and
name `idempotency-example-record`, parameter names `idempotency_key` and
`record_name`, step IDs `first_submit`, `repeat_submit`, `read_back`;
POST records twice with the same key/body;
first status 201, has id, name equality, Cache-Control equals no-store and
X-Internal-Debug absent; replay status 200 with original id/name; GET records
query name; status 200, count by name exactly one, count by original id and name
exactly one. Do not introduce stop-on-failure or alter these obligations.

Execute against a fresh synthetic target with complete, immediate list reads,
no name uniqueness constraint and no concurrent writer. The test harness owns
environment isolation. Add a separate Documents consumer using its existing
public envelope and distinct document vocabulary. Any synthetic target changes
must implement observable service behavior, not consult assertions or Scenario
IDs. Do not modify a real product to accommodate the framework.

## Required verification

1. Loader, both request locations, string values, empty values, references,
   duplicate names, invalid names/types/control injection/reserved names,
   unknown/extra params and contradictory response constraints.
2. Parameters, prior responses, included named results, caller substitution,
   expansion and impact; invalid/null/missing runtime values block atomically.
3. Real API capture: declared keys reach the target, case-insensitive names,
   exact and empty values; resolver/driver/normalizer/Recorder mutations cannot
   pass. Custom credential collisions reject before sending. No secret repr.
4. Approved retry/read example in backend+contract and explicit-API e2e;
   independently observed target requests; deliberately broken idempotency
   detected even when the replay response reuses the first ID. A separate
   synthetic Documents consumer proves the core is not records-specific.
5. Real Chromium fetch and XHR, live and mock: correct/wrong/missing headers,
   automatic extras, case variation, unknown evidence, duplicate asserted names,
   multi-request selection/ambiguity, background/replay, credentials forwarded
   without leakage, explicit mock response headers and wrong fixture controls.
6. Response equals/absent in all relevant paths and contract: absent versus
   empty, wrong values, None versus complete empty, repeated asserted/unrelated
   names, normalizer/Recorder changes; errors never reveal sentinel values.
7. Polling, continuation/stop, multi-user/session and inclusion regressions.
8. Full suite with real Chromium and no skip, fresh dev-only suite, maintained
   declarations and documentation samples, lock, hygiene including new files,
   diff/cached checks, independent audit and architect acceptance.

Record actual commands, outcomes, limitations and exact accepted file scope.
Only then perform the separately gated public branch/PR/CI submission workflow.
The capability is product-neutral, useful to unrelated records/documents
services, and repairs an expression/evidence gap rather than a behavior exception.
