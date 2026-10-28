# Refract Scenario Contract

A Scenario is a versioned acceptance baseline expressed as data: metadata,
parameters, and ordered primitive actions with expectations. It is not a complete
business truth or a script. Product preparation belongs in visible steps, not an
adapter's hidden workflow. Selectors, transport routing, session handling, and
truthful evidence normalization remain adapter responsibilities.

## Format and metadata

The executable format is `schema_version: 1`. This identifies the declaration
format, not a Scenario's content revision or approval. Unversioned declarations,
`version: 2`, and the former `actor`, `inputs`, `intent`, `precondition`, and `bind` YAML
fields are rejected; no silent conversion or compatibility mode is provided.

Format 1 now continues after ordinary assertion failure by default. This is an
explicitly approved execution-behavior change, not a claim that unchanged YAML
has unchanged behavior across engine revisions. Review existing stopping intent
and retain the engine revision with execution evidence. An include byte hash
alone does not pin engine semantics or renew approval.

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | strict integer `1` |
| `scenario` | yes | stable nonempty Scenario identifier |
| `description` | no | human-readable intent |
| `users` | yes | distinct logical account names or reserved `anonymous`; an empty list means no account binding |
| `parameters` | no | declared data values, optionally run-unique/time markers or bounded string composition |
| `grid` | no | organizational selector `{level, module}` |
| `steps` | yes | nonempty ordered list with unique step IDs |
| `results` | no | named aliases of this Scenario's own observed response fields |

Parameters contain finite JSON-like data, with explicit whole-value
forms described under [run values and string composition](#run-values-and-string-composition).
They are not scripts or a general generator registry. Unknown fields, duplicate
mapping keys, and invalid reference shapes fail validation.
A requested grid filter does not silently match a Scenario without that grid.

In positions that interpret references, keys beginning with `from_` are reserved:
an unknown spelling is a declaration error, not a literal expected object.
In authored parameter values those keys and `concat` are also reserved at every
dictionary depth, except inside an explicit whole-parameter `literal` wrapper.
The approved whole-parameter `from_run` and `concat` forms are parsed normally.
Wrapped data and runtime response objects are never reinterpreted as declaration
syntax. This
does not detect every possible typo or prove that an assertion expresses intent.

YAML 1.1-only implicit boolean aliases (such as `NO` or `yes`), sexagesimal
numbers (such as `12:30`) and leading-zero octal spellings (such as `017`) are
rejected. Quote them when strings are intended, or use an explicit decimal
number. This prevents silent reinterpretation without switching YAML dialects.

## Users and current sessions

Named users are logical account names, not roles, credentials, or declarations of
permissions. Exact lowercase `anonymous` is reserved for execution without an
account; it is never passed to the authenticator as an account name.
Account bindings belong to the adapter configuration. A response
field named `role` can still be checked when it is part of the business obligation;
the Scenario does not configure a user's role or grant permissions.

| Declaration | Step selection |
| --- | --- |
| `users: []` | Omit `user` and `session`; no authentication is performed. |
| `users: [creator]` | Omitted `user` selects `creator`; an explicit value must match. |
| `users: [anonymous]` | Omitted `user` selects anonymous execution; `session` is forbidden. |
| `users: [creator, anonymous]` or `[creator, peer]` | Every ordinary step must name a declared `user`, including waits. Include nodes select users through the rules below. |

Null, duplicate or non-string names, dynamic user selection, and undeclared users
are invalid. In a nonempty list, `anonymous` must be declared before a step can
select it. An explicit null or empty `user` is not anonymous shorthand. Before
business actions, the authenticator resolves each declared named user to a fixed
principal; anonymous participation has no principal or credentials. Different
named users must bind different principals.
This validates the adapter's declared identities, not the truth of a malicious
adapter's claims. Missing identity capability is an error, never anonymous fallback.

Authentication is lazy and projection-local. Omit `session` to keep that user's
current session. Set `session: new` on an ordinary step to authenticate the same
account again and replace only its current session. It must supply a new
authentication identity, not reuse the old one or select another account by role.
Blocked steps do not authenticate. Poll attempts reuse one session. A 401/403
response does not trigger automatic refresh or restoration of permissions.
There is no facility to return to an earlier replaced session. An anonymous leaf
cannot request `session: new`, including when a child alias maps to anonymous;
that declaration fails before any action rather than silently ignoring renewal.

The authentication port exposes `identify(user)` and `session(user)`. The latter
returns a `UserSession` with opaque `principal_id`, `authentication_id`, and
`credentials`. Core validates the first two and passes only the credentials to
execution adapters. Credentials and principal/authentication identities are
hidden from default representations; generic serialization is not safe.

UI execution retains separate contexts for each user's current session. Switching
users leaves other contexts open; a new session closes/replaces only that user's
context. Every remaining context is closed on exit. Anonymous execution uses its
own context, reusable only within that projection, and must not inherit
credentials, authenticated storage, or an existing user's context. Switching to
anonymous does not log out another user; switching back reuses that user's
retained session. Separate runs do not share anonymous contexts. No multiple
anonymous identities or explicit anonymous-context renewal are introduced.
Declaring anonymous execution is an instruction, not evidence that the target observed an
anonymous request. Login-page behavior and permission changes require their own
visible actions and assertions; authentication does not secretly perform them.

This format-1 cutover replaces the former `actor` declaration without conversion.
Maintained examples are migrated explicitly; historical records are not proof
that an unchanged declaration runs with the current engine.

The synthetic Documents examples exercise [owner versus same-role peer access](examples/documents/scenarios/owner_peer.yaml)
and [old versus new sessions after permission revocation](examples/documents/scenarios/permission_sessions.yaml).
Both reuse the same [single-user creation child](examples/documents/scenarios/shared/create_document.yaml).
Their target really enforces account ownership and the selected permission policy;
their 403 checks still do not prove an arbitrary product's rejection mechanism.
For a stronger response-level example, see [checking the stated rejection reason](docs/rejection-evidence.md):
it distinguishes an ownership code from login, input, missing, or conflicting
reasons without claiming independent internal-decision evidence.
The [named-peer caller](examples/documents/scenarios/mapped_peer_access.yaml) and
[anonymous caller](examples/documents/scenarios/mapped_anonymous_access.yaml)
reuse the same [two-participant child](examples/documents/scenarios/shared/access_document.yaml)
with explicit mappings. Its shared refusal accepts 401 or 403 only; each parent
adds its own exact status and response-code requirement. These are deliberately
different approved obligations, not an automatic relaxation of a fixed 403 check.

## One action per step

There is no `action`, `type`, or `sequence` wrapper. An executable leaf step has
one `id`, one `do`, the applicable action fields below, and optionally `expect`,
`user`, `session: new`, and `on_failure: stop` under the user rules above.
A static include is a composition node expanded into these same leaves before
execution, not a multi-action adapter primitive.

| Action | Declaration | Meaning |
| --- | --- | --- |
| Open | `do: open`, `target` | open one logical page |
| Click | `do: click`, `target` | activate one logical control |
| Fill | `do: fill`, `target`, `value` | fill one logical input |
| Wait | `do: wait`, `duration` | core waits a nonnegative integer number of milliseconds |
| API request | `do: {request: {method, path, query?, headers?, body?}}` | send the declared request |

Targets map to elements, not multi-action business scripts. A click must not
secretly navigate, fill fields, and submit. Wait does not trigger a scheduled
job, change the host clock, or assert success.

An API action stores its request under `do.request`, never under `expect`.
A UI action may declare `expect.request` to constrain the traffic it causes.
The same step cannot contain both request forms. Requests use an HTTP method,
an explicit list of logical path segments, optional query and business-header
mappings, and an optional body mapping.
Each path segment is encoded separately after resolving references.
Standalone `.` and `..` segments are invalid: transports can normalize them to
a different resource. Known literal/parameter segments fail loading; unusable
response-derived segments block their consumer before action. Encoded literal
percent data and ordinary punctuation are not dot-segment navigation.

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

### Request query parameters

Both `do.request` and a UI action's `expect.request` accept `query`. Keys are
nonempty literal strings. Each value is a string, integer, boolean, finite float,
or an existing parameter, prior-response, or included-result reference resolving
to one of those types. Empty strings, zero, and false remain values. Null, lists,
mappings, non-finite numbers, dynamic keys, repeated keys, and extra reference
syntax are invalid. Known invalid values fail loading, including child parameter
overrides. Runtime response values invalid for query use block the consuming
action atomically under the existing dependency policy.

```yaml
- id: next_page
  do:
    request:
      method: GET
      path: [records]
      query:
        category: {from_parameter: category}
        limit: 1
        cursor: {from_step: first_page, response_field: next_cursor}
  expect:
    response:
      - check: success
```

This fragment assumes a declared `category` parameter and an earlier
request-bearing `first_page` step. The complete executable
[Documents filter and next-page example](examples/documents/scenarios/filter_and_next_page.yaml)
visibly creates three records, filters two matching records, and requests each
page in a separate step. Run it against a fresh isolated target with creation-order
lists; the harness owns isolation and disposal. No adapter reset, cleanup,
automatic pagination, expression, or loop is implied.

Query comparison uses decoded wire strings. Strings stay unchanged; integers
use decimal spelling, booleans use `true`/`false`, and finite floats use JSON
numeric spelling. Thus integer `1` and string `"1"` have the same query-string
representation; boolean `true` and string `"true"` also match on the wire.
Body and response checks retain strict JSON types: `1`, `"1"`, and `true` do
not become interchangeable there. Key order is not semantic. Transport encodes
each key and value once using standard URL encoding, preserving blanks and
encoded delimiters as data. Observed URLs decode percent escapes and plus-space
encoding; malformed escapes, invalid UTF-8, and duplicate decoded keys are
execution errors. A bare wire key may represent an empty string.
Empty separator-only chunks, as in `a=1&`, carry no parameter and are ignored;
a real empty-name parameter such as `=value` is still invalid.

| Request location | Omitted `query` | `query: {}` | Nonempty `query` |
| --- | --- | --- | --- |
| API `do.request` | Send no parameters | Send no parameters | Send exactly these values |
| UI `expect.request` | Keep method/path/body-only scope | Require no parameters | Require exact decoded equality, including no extra keys |

Resolvers map routes and preserve the declared query meaning. They cannot read
global parameters to invent query business values, add defaults, drop values, or
override them. Authentication remains in the session port. A resolved request
path cannot contain a second embedded query or fragment. Backend verifies this
ownership before sending and checks returned and Recorder request evidence
against the protected outgoing request. Drivers encode at transport time without
changing that evidence. Actual transport paths are adapter evidence, not an
independent witness of a malicious driver's behavior.

`RequestTemplate.query` retains declaration values and references; `None` means
omitted. `RequestSpec.query` is a keyword-only mapping of decoded wire strings,
defaulting to a fresh empty mapping. It contains actual request evidence, never
values filled from an expectation. Query participates in atomic preparation,
inclusion rewriting, named results, instantiated validation, expanded review,
and change-impact inspection. The shared `refracto.query` utility supplies
validation, serialization, URL encoding, and observed parsing. Runtime query
values are sensitive and hidden from default request representations.

### Business request headers

Both request locations accept `headers`. Names are literal ASCII HTTP token
names, compared case-insensitively; duplicate names with different casing are
invalid. Values are strings or existing parameter, prior-response or included
named-result references resolving to strings. This bounded sender accepts empty
or visible ASCII strings with internal spaces, not surrounding whitespace,
control characters, non-ASCII values, or implicit number/boolean conversion.
Known invalid values fail loading; unavailable or invalid response-derived
values block the dependent step before sending. No new reference source exists.

```yaml
- id: submit
  do:
    request:
      method: POST
      path: [records]
      headers:
        Idempotency-Key: {from_parameter: idempotency_key}
      body:
        name: {from_parameter: record_name}
  expect:
    response:
      - check: status_equals
        value: 201
      - check: header_equals
        header: Cache-Control
        value: "no-store"
      - check: header_absent
        header: X-Internal-Debug
```

This fragment assumes the two declared string parameters. The complete
[retry/read example](examples/minimal/idempotent_create.yaml) sends one key and
body twice, compares the returned IDs, then counts all records matching the
name and those matching both the original ID and name. It uses a fresh isolated
synthetic target with complete, immediate list results and no name uniqueness
constraint. A reused fixed test key or a truncated list could invalidate that
reasoning. These are explicit harness/target assumptions, not hidden adapter
preparation or general database/concurrent-idempotency guarantees.

For API actions, resolvers must preserve exactly the declared business-header
mapping, allowing only name casing differences. Reference drivers combine it
with independently owned session and transport headers and capture the actual
request. For UI actions, declared headers constrain a subset of the actual
browser headers; automatic or other undeclared headers are allowed. Omission
or `{}` adds no header constraint, unlike `query: {}` which requires no query.
Expectations never inject or repair the browser's outgoing headers.

Credentials and transport control are not business inputs. Declarations reject
Authorization, Proxy-Authorization, Cookie, Set-Cookie, Host, Content-Length,
Content-Type, Transfer-Encoding, Connection, TE, Trailer, Upgrade, Expect,
Accept-Encoding, Origin, Referer, User-Agent, Traceparent and Tracestate, and the
`proxy-`, `sec-`, and `x-refract-` prefixes, case-insensitively. Adapters also
reject collisions with their custom session credential headers before sending
or performing the constrained UI action. There is no silent precedence rule.

`RequestTemplate.headers` holds declared values/references; `RequestSpec.headers`
is a keyword-only business mapping with an independent empty default. Actual
raw header evidence lives separately on `RecordedResponse.request_header_items`
and `RecordedResponse.header_items`: complete ordered name/value pairs, or None
when unavailable. An explicit empty list means an observed complete empty block.
Flattened dictionaries and normalizer output cannot substitute for those lists.
Drivers must capture actual transport data, not fill observations from assertions.
Complete means the identified observation point, not network packet capture.
The browser helper captures the full browser-provided request block and its
effective trace/private-marker rewrite. Its forwarding transport may add owned
headers such as Host or Content-Length; those additions are not invented as
observations and cannot be declared as business inputs. Independent peer tests
verify the supported business values received by the target. API capture is
from the sent request object or exact in-process target invocation. No core
mechanism can independently prove a driver's consistently fabricated evidence.
Recorded raw blocks can contain credentials; all new fields and the legacy
response-header map are hidden from default representations and marked sensitive.
Do not serialize entire requests, recordings or reports generically.

### Request constraints

A UI step's `expect.request` constrains method, logical path, and declared body
fields. Mapping comparisons are recursive subsets: additional transport fields
are allowed. Arrays require equal length and order with type-strict recursive
elements; mappings inside arrays remain subsets. Scalars require identical types
and values. A mapper must not invent
undeclared business inputs to satisfy the constraint.
Declared query equality follows the exact decoded-string rules above, not the
body's recursive subset comparison. Browser request evidence is extracted from
the actual URL independently of these expected values.
Declared business headers use case-insensitive names and exact string values
against the complete actual request block. A missing or wrong value is a failed
check; unavailable, malformed or repeated asserted-name evidence is an execution
error. Unrelated repeated headers do not change another name's assertion. Where
multiple requests already belong to the same action and method/path, explicit
query and header constraints may identify exactly one; missing or ambiguous
selection is an error. Background traffic never becomes action evidence.

### Response vocabulary

| Check | Parameters |
| --- | --- |
| `success` | none |
| `failure` | none |
| `status_equals` | `value` |
| `status_in` | `values` |
| `header_equals` | `header`, `value` |
| `header_absent` | `header` |
| `has` | `field` |
| `field_equals` | `field`, `value` |
| `field_not_equals` | `field`, `value` |
| `field_compare` | `field`, `op`, `value` |
| `collection_length` | `field`, `op`, `value` |
| `field_absent` | `field` |
| `collection_matching_count` | `field`, `matching`, `count` |

`success` and `failure` check the normalized success indicator and cannot coexist
in a step. `failure` means that indicator is false; it does not establish why a
request was rejected or whether an authorization decision was reached. Add the
actual response and state requirements needed for the intended obligation.
`has` checks presence. `field_equals` and `field_not_equals` both require the
field to exist, then compare its complete type and value. These are normalized
fields, not arbitrary raw JSON paths.

### Complete response-field comparison

These two checks accept finite JSON-like values: null, booleans, integers,
finite floats, strings, lists and string-keyed objects, recursively. Expected
values may be literals or use the existing parameter, prior-response and
included-result references, including references inside a declared container.
Runtime response data that resembles reference syntax remains data.

Objects must have exactly the same keys and recursively equal values; key order
does not matter. Lists must have the same length, order and element values.
Extra object members are not ignored. Types are strict: `false` differs from
`0`, and `1` differs from `1.0`. There is no sorting, coercion, subset matching,
arithmetic or approximate comparison. This extension does not broaden other
assertion parameters or request path/query/header values.

The following fragment assumes an earlier request-bearing `read_before` step
that guarantees `content`, and an `attempted_content` parameter:

```yaml
- check: field_equals
  field: content
  value: {from_step: read_before, response_field: content}
- check: field_not_equals
  field: content
  value: {from_parameter: attempted_content}
```

A missing current field fails either check: missing evidence cannot prove
inequality. A present null or empty object/list is a value, not absence.
Missing source evidence and top-level null response references still block the
consuming step before its action; this task does not change that reference rule.
Non-finite, cyclic or otherwise unsupported observed values produce an execution
error, even if their types differ. Invalid response-derived expected values block
the consumer. Core retains stable normalized snapshots so a later callback cannot
rewrite an earlier comparison baseline through a reused mutable container.

One equality and one inequality may coexist on the same field; both are checked.
Repeating the same check on that field, or combining either with `field_absent`,
is invalid. Ordinary comparison failures continue under the existing policy;
`on_failure: stop` remains available. New container and inequality diagnostics
name the field and reason without dumping nested keys or values. This is not a
general-purpose redaction or serialization system.

See the complete [rejected-update example](examples/minimal/rejected_update_preserves_content.yaml)
and its separate [Documents consumer](examples/documents/scenarios/rejected_update_preserves_content.yaml).
The final read compares actual content with the first read and with the attempted
replacement. Success/status/object-ID controls prevent identical error responses
or a different object from establishing the unchanged-content claim. This proves
only the selected normalized content, not all database state or an independently
observed authorization decision.

### Numeric fields and list lengths

`field_compare` compares one actual normalized numeric field with a threshold.
`collection_length` compares the length of an actual normalized list. Both use
`field`, `op` and `value`; `op` is `>`, `>=`, `<`, `<=` or `==`. The field name
is a nonblank literal, not a path. Thresholds use existing literals, parameters,
prior-response references (including member selection) or included named results.
There is no arithmetic or new reference syntax.

For example, with a declared integer `page_size` parameter:

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

Numeric operands are finite integers or floats, excluding booleans. Ordering
compares integer/float numeric values without converting large integers to
floats; `==` keeps type-strict equality, so 1 differs from 1.0. Negative numbers
and zero are valid. Numeric strings are never converted.

List-length thresholds must be nonnegative integers, excluding booleans and
floats such as 1.0. All elements count, including duplicates, nulls and mixed
finite JSON-like members. Only a list is measured: strings and mappings are not
collections for this check. Length does not filter members, fetch other pages,
prove database totals or assert the types of individual members. Keep existing
`collection_matching_count` checks when exact content matters.

| Evidence or declaration | Result |
| --- | --- |
| Current field missing, null, or a valid JSON-like value of the wrong type | FAILED |
| Valid operands outside the declared bound | FAILED |
| Invalid fixed threshold or parameter, including an include override | DeclarationError before execution |
| Unavailable or invalid response-derived threshold | Local BLOCKED before action, without partial bindings |
| Examined data contains non-finite numbers, cycles, unsupported objects or invalid mapping keys | ERROR |
| Malformed normalizer port output | ERROR under the existing port rules |

Missing evidence is never zero or an empty list. Validate the examined value's
finite JSON-like data even when its type is wrong or a comparison would otherwise
be trivial. Unrelated normalized fields do not acquire a new restriction.
Ordinary failures continue unless `on_failure: stop` is declared; existing
dependency blocking and ERROR/SKIPPED stopping rules remain.

Multiple bounds are retained and all checked. Repeating the same check, field
and operator is invalid, as is combining either check with `field_absent` on
that field. There is no automatic range simplification. Existing equality,
matching-count, UI-count and span comparison behavior is unchanged.

Backend, API/live UI e2e, frontend mock responses and polling share these checks.
Contract retains each constraint and reads actual provider values; unavailable
or invalid referenced thresholds never pass or trigger a replacement request.
Verified unexecuted consumers remain visibly BLOCKED; an impossible reference
for an allegedly executed consumer is an error, without erasing independent
endpoint checks. Contract is not an independent observer. New details
name the field, operator and reason without printing operands or list contents;
this does not promise safe arbitrary serialization or change older diagnostics.

See the [complete Documents pagination example](examples/documents/scenarios/check_page_limits.yaml)
and the [independent Records declaration](examples/minimal/check_page_limits.yaml).
Their preparation is explicit, with an isolated empty target and creation-order
lists. `returned` describes the current page, not the filtered total. Reported
count bounds and actual list-length bounds are separate checks, not a new
same-response arithmetic or consistency relation.

### HTTP response status and headers

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

`header_equals` requires one actual header with an exactly equal string value;
its value accepts the existing references resolving to strings. `header_absent`
requires no occurrence of the literal header name. Names are case-insensitive,
but values are not trimmed, split on commas or interpreted. A present empty
value fails an absence check. For example, `private, no-store` does not equal
`no-store`. Duplicate constraints or equals/absent on the same case-folded name
are invalid declarations.

These checks use complete raw header pairs captured before normalization.
Unknown evidence cannot prove absence. Multiple occurrences of an asserted
name, even with equal values, are unsupported evidence and cause ERROR;
unrelated repeated headers remain allowed. Valid evidence with a missing or
unequal equals target, or a present absence target, produces FAILED. Details do
not expose observed or expected header values. Polling checks each actual
attempt. Mock headers must come from explicit fixtures and actual fulfilled
browser responses; they are not live backend evidence. No response-header
reference syntax or multi-value interpretation is introduced.

`field_absent` checks membership, not truthiness: a present null, zero, false,
empty string, list, or mapping fails. Failure details name the field, not its
value. Duplicate absence checks, or absence combined with `has`,
`field_equals`, `field_not_equals`, `field_compare`, `collection_length`, or
`collection_matching_count` on the same field, are invalid.

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
response reference blocks the consuming step before its action. Literal null or
a null parameter may be matched, but a missing member field is not null. Existing
missing/null prior-response references likewise cause local `BLOCKED`, not a
passing or silently omitted check.

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

The normalizer must return a `NormalizedResponse` with a boolean `succeeded`
and a string-keyed dictionary of fields. Malformed port output is an execution
ERROR, not an ordinary assertion mismatch or a recoverable missing reference;
contract also reports it as an error. This structural check does not certify the
truth or completeness of the adapter's normalization.

### Backend-state vocabulary

| Check | Parameters |
| --- | --- |
| `span_exists` | `span` |
| `span_attr` | `span`, `attr`, `op`, `value` |
| `object_field_equals` | `object`, `id`, `field`, `value` |

`span_attr` uses `>`, `>=`, `<`, `<=`, or `==`; ordering requires finite numeric
operands, excluding booleans and numeric strings. Unsupported observed types
cannot satisfy the check. Supported reference comparisons use equality. StateProbe remains separate
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

### Business-object state observations

The [create/read/storage example](examples/sqlite_records/scenarios/create_and_verify_storage.yaml)
checks a semantic `record` by the actual ID returned by the preceding create
step. `object` and `field` are nonempty literal business names, not table or
column names. `id` uses an existing value reference, resolving to a nonempty
string or exact integer; bool, null, empty strings and containers are invalid.
`value` is a finite scalar or an existing reference to one. Direct `concat` is
not accepted in this new assertion's `id` or `value`; referencing an already
composed parameter is allowed. Equality preserves
types, including false versus zero and explicit null versus an absent field.
Known invalid inputs fail loading; unavailable or invalid prior-response inputs
block their consuming step before its action. No current-step self-reference,
dynamic field name, SQL, additional include level or storage configuration is
introduced. The frontend assertion of the same name still uses its existing
`anchor` parameter and keeps its UI meaning.

Wire the separate optional `Adapters.object_state` to an `ObjectStateProbe`.
Core groups checks by semantic object and exact ID type/value, requests their
fields once, and evaluates them against a single returned snapshot. The probe
receives only object/ID/field selection and execution identity, not expected
values or assertions. Its mapping to concrete storage and its read-only
connection belong to the adapter. Existing trace-based `StateProbe` checks are
unchanged; database observations are never represented as fabricated spans.

Observation occurs after the step's real response, even if an ordinary response
assertion failed. A successful terminal API poll leads to one object lookup;
an unsuccessful poll or SKIP does not. Object lookup does not retry until a
value matches and does not inherit span polling. This slice covers synchronous
committed state, not eventual-consistency waiting. Different objects need not
share a transaction; multiple fields on the same object must share a snapshot.

A complete lookup with no object, an absent field or an unequal value fails the
check. Ambiguous matches, wrong query/object identity, query exceptions,
incomplete observations and malformed facts cause ERROR. An absent object probe
is visible degradation and cannot pass the strict gate. Backend and live e2e
share this evaluation. Frontend mock execution and contract do not query storage
and mark these declarations outside their checked scope.

`StepResult.state_observations` retains copied facts, the observation's identity
and source label, hidden from default repr as sensitive data. It is not a new
reference source or include result. Identity echo and source labels establish
local correspondence, not truth authentication. A matching stored row proves
only the observed values at that time; it does not by itself prove the entire
causal history, future durability or correctness of an arbitrary adapter.

## Parameters and prior response values

The local reference forms are `{from_parameter: record_name}` and
`{from_step: submit, response_field: id}`. An included Scenario's public result
uses `{from_step: setup, result: record_id}` as described below. They can occur in action values, path
segments, query values, body values, and supported assertion values. A response reference names
an earlier request-bearing step and reads its actual normalized runtime response,
never its expected value. A source step need not assert `has`: preparation
requests may supply values without inventing checks.

Missing or null response fields, unavailable source steps, and response-derived
values invalid for their use position produce local `BLOCKED` atomically, with
no action or partial resolved mapping. Independent later steps can still run.
A source step's failed assertion alone does not make its actual response
unavailable. Zero, false, and empty strings remain valid where the position
accepts them; an empty or boolean path segment is still invalid. No user-managed
binding aliases, general expressions, arithmetic, JSONPath, reference-valued
mapping keys, or coercion are supported. Only the bounded `concat` form below
composes strings. Frontend references read mock responses,
which remain distinguishable from live responses.

### Run values and string composition

The [maintainer's R1 revision of 2026-10-27](docs/roadmap.md#maintainer-decision-r1-revision-2026-10-27)
allows composition and prohibits transformation: bounded `concat` joins strings
without changing any operand's content. It is legitimate under revised R1, not
an exception. Formatting, timezone conversion, truncation, case conversion,
arithmetic, templates, conditions, and missing-value fallbacks are not enabled.
Existing parameter declarations and run-value sources retain their contracts.

**Committed scope:** parameter-level `concat` whose operands are string literals
or references to string-valued parameters. Other currently accepted composition
forms are outside this commitment. In particular, step-level concat with
prior-response operands (`from_step` with `response_field`), and concat in
assertion-value positions, are **frozen: retention is not promised**. They remain
accepted by the current loader and execution engine. This governance decision
does not remove syntax, change runtime behavior, or change `schema_version: 1`.
Further support requires a concrete use case and separate review.
Requests and assertions may still use ordinary `from_parameter` references to
a committed composed parameter. The frozen assertion form is `concat` declared
directly in an assertion value, not a reference to that parameter.

Declare a unique-value source and reuse its value through ordinary parameters:

```yaml
parameters:
  run_token: {from_run: unique}
  document_title:
    concat:
      - {from_parameter: run_token}
      - "-document-"
      - {from_parameter: run_token}
```

`from_run` is recognized only as the entire value of a directly declared
parameter. `{from_run: unique}` requests the token described here; the bounded
`time` form is described below. There is no `prefix`, `suffix`, custom generator,
time format or step-level `from_run` reference.
Loading, validation, expansion and impact inspection do not generate anything.
Each independently declared unique parameter generates its own opaque 32-character
UUID4 hex string. Within an execution, every reference to that parameter, including
poll attempts, uses the frozen value. Backend, frontend and e2e each bind their
own values; contract reuses backend's values and recordings. Another invocation
generates new values. Preparation of all selected executions finishes before
adapter calls. These strings are neither server object IDs nor credentials, and
do not prove absolute collision impossibility or target-state isolation.

`RunReport.run_unique_values` records projection names mapped to compiled unique
source parameter names and actual values. Contract records a separate copy of
backend's mapping. The bound Scenario has a flat `run_unique_values` mapping.
These fields are hidden from default repr and marked sensitive; arbitrary
parameters and composed business strings are not automatically recorded. This
replaces the former single `run_unique` field. Generic report serialization is
not a safe export. Independently authored frontend fixtures are not rewritten
from expected values or automatically populated with generated data.

`concat` consists of exactly one key with a nonempty operand list. Each operand
must be a literal string or a supported reference whose actual value is a string.
There is no nested concat syntax, implicit number/boolean/null conversion,
template interpolation, arithmetic, function call, conditional or fallback.
Empty strings remain strings; the destination still decides whether an empty
result is usable. Parameter-level concat can refer only to declared parameters,
including forward declarations, with cycles and unknown names rejected. A plain
parameter mapping containing `from_parameter` is rejected, not treated as an
alias or silently sent as data. A string alias can use a one-operand concat.

Ordinary parameter values are finite JSON-like data, but dictionaries containing
a `from_`-prefixed key or `concat`, at any depth including inside lists, require
an explicit whole-parameter `literal` wrapper. It has exactly one key; mixing it
with other keys is invalid. Only the outer wrapper is recognized. Everything
inside is copied as data, including further `literal`, `from_run` or `concat`
objects, without interpreting it. Parameter names and ordinary string contents
are not reserved. For example:

```yaml
parameters:
  payload:
    literal:
      meta: {from_run: unique}
      items: [{from_parameter: ordinary-data}]
```

Here `payload` is the actual dictionary containing `meta` and `items`; it does
not generate or reference anything. Scalars, null, false, zero, empty strings,
arrays and objects retain their types when wrapped. Normal destination type
rules still apply. A nested `literal` key in an unwrapped parameter is not an
escape. The wrapper is not a new step-level value form. Actual responses and
values obtained from references are never parsed again as declaration syntax.

The following describes an implemented but frozen form, outside the commitment
above: in later steps, concat can combine earlier actual response strings.
**Retention is not promised; this example documents current acceptance rather
than recommending new use.**

```yaml
concat:
  - {from_step: account, response_field: account_code}
  - "-document-"
  - {from_step: batch, response_field: batch_code}
```

This value can occupy existing string-capable positions, such as a body value,
path segment, query/header value, fill value or supported assertion value. These
uses remain subject to the frozen status above, including direct assertion-value
concat. It does not turn a request body or query container into a string, change numeric
assertion types, allow dynamic keys, or replace a reference-only identity slot.
Response operands can use the existing dictionary/member and named-result forms;
their sources must still be earlier request-bearing steps. Parameter declarations
cannot read responses that do not yet exist.

Known malformed expressions and nonstring operands fail loading. Missing, null
or wrong-type response operands block only the consumer before action, with no
partial bindings or manufactured empty string. Composed values undergo normal
path/query/header and assertion-position validation. Actual responses remain
unchanged; neither their dictionaries nor literal parameter data are reparsed.

Included parameter defaults retain child scope. Overrides affect their dependent
compositions; response-dependent overrides resolve at the consuming leaf, not
at run start. Repeated includes generate separate default unique values; explicit
parent references in `with` retain their parent source and share its value.
Passing the same value twice deliberately can still cause a duplicate creation.
Independent parent parameters generate independently, even with identical
`from_run` spelling. No new result interface or inclusion level is introduced.
Low-level projection callers must explicitly freeze declarations first with
`bind_run_values`; its return is `(bound_scenario, unique_values)`, with a flat
mapping rather than the former single token. Unbound run markers are errors,
never implicit generation inside a projection. Binding an already-bound Scenario
is rejected; retain the symbolic declaration for a fresh execution. Offline
contract checking reuses the frozen backend Scenario and recordings.
Keep the original declaration for authoring review: `expansion_view` rejects
already-bound run models rather than exposing their runtime values as literals.

See the executable [Documents](examples/documents/scenarios/run_unique_create_locate_read.yaml)
and independent [Records](examples/minimal/run_unique_create_locate_read.yaml)
create/locate/read examples. Repeated runs may retain old objects, but selection
still needs actual unique matching evidence. Independent generated values do not
clean up data, make duplicate matches acceptable or isolate all target state.
Fixed or explicitly shared business values can still collide across writers;
the test host owns environment isolation.

### Run-relative UTC time

Declare time inputs as direct parameters and reuse them through ordinary
`from_parameter` references:

```yaml
parameters:
  expires_at: {from_run: time, offset: {days: 7}}
  window_start: {from_run: time, offset: {hours: -24}}
  window_end: {from_run: time}
```

One selected logical run reads its UTC wall clock once. Every time parameter,
included leaf, selected projection and polling attempt uses that same base.
A subsequent invocation reads anew; two runs may share a millisecond. An omitted
`offset` means zero. An explicit offset has exactly one unit (`days`, `hours`,
`minutes` or `seconds`) and a strict signed integer. Zero is valid; booleans,
floats, strings, null, empty/multiple units and additional keys are rejected.
A day is exactly 24 hours, not a calendar day or business day. There are no
month/year operations, timezones, format templates or dynamic offsets.

The base is truncated to milliseconds once, then offsets are applied. Values
are strings in the fixed format `YYYY-MM-DDTHH:MM:SS.sssZ`, such as
`2026-10-24T08:00:00.000Z`. Impossible offset ranges fail declaration loading;
overflow from a valid offset and the chosen base fails before any port call.
Ordinary strings and explicitly wrapped marker-looking dictionaries remain data. Existing
concat can consume a resolved time through a parameter reference; it does not
parse or calculate time. `field_compare` still accepts numbers only.

For fixed-input replay, pass the optional `run_time` keyword to `run_scenario`:

```python
report = run_scenario(
    scenario_path, adapters, projections=("backend", "contract"),
    run_time="2026-10-24T08:00:00.000Z",
)
```

The value must be a real date in that exact UTC millisecond string format.
Invalid values fail configuration without fallback or target side effects.
An invalid supplied timestamp, an unavailable UTC clock, or an offset that
overflows the selected base raises `ValueError` before projection execution;
these preparation failures do not return a `RunReport`. A caller must treat the
exception as an unsuccessful invocation, not as a passed or empty test run.
Omission uses actual UTC time only when the selected declaration has a time
marker, including an unused declared marker. Loading, validation, expansion,
impact inspection, filtered runs and declarations without time markers never
read the wall clock. This does not change `now`, the monotonic polling clock.
There is no new CLI option.

The report records `run_time`, `run_time_source` (`actual` or `fixed`) and
`run_time_values` (compiled direct-time parameter names and resolved values).
These are explicit sensitive metadata, hidden from default repr, not an export
of all parameters. Generic report serialization remains unsafe. Included
parameters retain their scopes and override behavior. A fresh bound declaration
keeps execution values separate from symbolic authoring views; offline contract
uses that same bound declaration without reading another clock. Independent
projection callers use `bind_run_values(..., run_time=...)` first; its existing
two-item return contains `(bound_scenario, unique_values)` under the scoped
unique-value rules above. Time metadata records direct time sources, not aliases
which merely reference a parent parameter.

The [Records expiration example](examples/minimal/create_expiring_record.yaml)
checks creation and readback of the declared expiration. It does not prove that
the record expires later. The
[Documents recent-window example](examples/documents/scenarios/query_recent_documents.yaml)
declares the query interval and basic response checks. A success code and list
length do not prove filtering: its separate synthetic consumer tests check
known inside/outside and boundary records and reject faulty filters.

Fixed time freezes inputs, not the host clock, server clock, stored data,
sessions or unique tokens. A real server may reject a fixed historical expiration
as expired. Replaying the time input alone does not reproduce a whole system.

### Dictionary keys and unique collection members

A whole-field reference is unchanged. Add a literal `key` to read one member of
an observed dictionary:

```yaml
from_step: create
response_field: record
key: id
```

This reads the actual `record` dictionary's `id`, not a top-level `id` and not an
expected value. Without `key`, the reference returns the entire `record` value.
`key` must be a nonblank literal string. A dot or slash is part of that literal
key, not a nested path. A selected object/list can be used whole at positions
that already allow it, but selection cannot continue into it.

For an observed list of objects, use both `matching` and `member_field`:

```yaml
from_step: locate
response_field: records
matching:
  code: {from_parameter: record_code}
member_field: id
```

Every predicate must match the same member, using the existing type-strict
`collection_matching_count` rules. Exactly one member must match; the reference
then reads its literal `member_field`. No `count`, index, first-item fallback,
sorting or extra request is involved. This checks only the observed response/page,
not all pages or global database uniqueness. The normalizer must retain the
observed collection, not choose its member using Scenario expectations.

Matching values accept finite scalar literals, parameters, ordinary prior
response-field references and included named-result references. Literal or
parameter null may match a present null, but not a missing member key. New
selectors cannot be recursively nested inside matching values. Known nonscalar
predicates fail loading; unavailable/nonscalar response-derived predicates block
the consuming step.

The three reference shapes are exclusive: `key` cannot accompany `matching` or
`member_field`, and both list-selector fields are required together. Unknown
fields, dynamic keys, forward/self sources, and selector additions to parameter
or included-result references are invalid. Sources remain earlier local
request-bearing steps. Named-result definitions keep their existing two fields;
this extension does not expose child internals or change that interface. Child
steps may use selectors internally, and callers may pass selected values through
existing `with` parameters. Expanded review retains the selector meaning.

A wrong container type, malformed list member, missing key/member field,
zero/multiple matches, selected null or unusable selected value produces atomic
local `BLOCKED` before the consuming action, with no partial resolved bindings.
Selection verifies uniqueness itself even without a preceding count assertion.
Zero, false and empty strings are preserved where permitted; paths still reject
booleans and empty strings. Whole objects/lists remain finite JSON-like values,
and runtime data resembling reference syntax is never executed. Evidence is not
mutated, and mutable selected values are isolated from later callbacks.

New selection diagnostics explain the source and structural reason without
printing matching values or selected contents. This is not a guarantee for
generic serialization or all existing scalar assertion details. Backend, e2e,
frontend mock references and contract share the selection rules; contract uses
actual provider evidence, not expected data or a new independent observation.

See the complete [create/list/update/read example](examples/minimal/create_locate_update_read.yaml)
and [dictionary reference example](examples/minimal/dictionary_record_reference.yaml).
Those older examples use fixed record codes and require an isolated target with
those codes initially unused; they do not opt into run values or hidden preparation.

## Including a pinned, reviewed Scenario

A Scenario may include all steps of a local single- or multi-user child, mapping
its local participants to declared parent participants. The child must independently
validate, contain an effective assertion, and have no include of its own.
No recursion, dynamic target, partial inclusion, assertion override, or execution
cache is supported.

The include step accepts only `id`, `do: {include: <literal Scenario ID>}`, and
optional `with`, `user`, or `with_users` under the selection rules below. No session override
is allowed on the include node. For example, in a single-user parent declaring
a `record_name` parameter:

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
invocation has isolated parameters and steps; explicitly literal parameter
objects resembling reference syntax remain data when passed by reference.
No additional parameterized positions are introduced.

If a child declares `users: [operator]`, two parent include steps may select
`user: creator` and `user: peer`. Both reuse the same child bytes: `operator` is
bound to the selected parent user, not a separately authenticated account.
Explicit and implicit child user selections map identically. A child's own
`session: new` remains effective for that mapped user. Caller review includes
this user choice; an unchanged child pin does not approve a new caller binding.

A multi-user child requires a complete `with_users` mapping, even when parent
and child names are identical. A single-user child may also use this explicit
form instead of the shorthand. For a child declaring `users: [creator, reader]`,
a parent declaring `users: [creator, anonymous]` can use this include fragment:

```yaml
- id: access
  do: {include: documents.shared_access}
  with_users:
    creator: creator
    reader: anonymous
```

Keys are exactly the child's declared participants; values are literal declared
parent participants. No missing/extra keys, dynamic values, unknown targets,
or duplicate targets are accepted. An include cannot combine `user` with
`with_users`; ordinary steps cannot use `with_users`. A parent with `users: []`
has only the implicit anonymous target. A child with `users: []` uses anonymous
shorthand without an empty `with_users` mapping. An explicitly or implicitly
anonymous child participant cannot map to a named account. A named child alias
may map to anonymous only if all its unchanged session rules permit it.

Each child leaf selects its own local participant before applying this mapping;
one caller selection never overwrites all child users. Distinct child participants
cannot collapse to one target, including anonymous. Named-account identity checks
also reject two parent aliases configured as one principal. Mapping changes
require caller review even when the child bytes and pin are unchanged. Mapping a
fixed-403 child to anonymous does not make an actual 401 satisfy that assertion.
No child action, expectation, failure policy, or session policy can be overridden.

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
not read or checked implicitly. A consumed missing/null field causes atomic local
`BLOCKED` before the consuming action; falsy values survive subject to that
position's type rules. Ordinary child FAILED does not itself block a parent
consumer of an available result. Child ERROR, SKIPPED, or FAILED with explicit
`on_failure: stop` blocks all remaining leaves in that projection. Every
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
parent retains its user declarations, metadata, grid selection, adapters, and projections.
Child grid metadata cannot silently filter steps. Sessions and UI contexts belong
to the effective parent users. All child actions and checks remain present; unsupported expanded
flows still fail the existing projection checks before side effects.

Ordinary FAILED continues by default. A child's explicit leaf `on_failure: stop`
is preserved during expansion and stops later child and parent leaves; the parent
include node cannot override it. ERROR and SKIPPED also stop the projection.
Local unavailable-reference BLOCKED only prevents consumers that need unavailable
evidence. Inclusion is not
a transaction: a runtime-only argument error occurs before its consuming action,
and earlier actions may already have run. There is no rollback or hidden setup.
No parent-only assertion is mechanically required when the child already supplies
effective checks, but that does not establish the parent's complete business goal.

`refracto validate <parent.yaml> --expand` explicitly prints the verified flat
review plan and its sources. It preserves symbolic response references and shows
declared public result names, their source mappings, and each leaf's effective
failure policy, explicit anonymous selection, effective user, session policy,
and the complete included local-user mapping.
It never runs adapters,
and emits no partial plan when validation fails. This is a review
view, not another authoring format. It can display literal declaration data,
including `with` values; its confidentiality matches the source files. It never
contains runtime response values. Default validation remains a concise summary.

Qualified leaf IDs remain in reports and contract identity. The loaded Scenario
and RunReport expose `source_lookup`, a diagnostic map with source Scenario ID, original
step ID, include step ID, source-byte SHA-256, and local/effective user mapping.
This does not affect equality,
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
evaluate against that response. Every attempt reuses the prepared query and
retains its actual request query in the recording.
On either timeout policy, declared state checks are listed as not checked because
there was no successful terminal response; no state evidence is fabricated or
queried against a non-final attempt.

```yaml
schema_version: 1
scenario: demo.export_ready
users: [user]
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

### Continuing and stopping

Steps run in order. By default, an ordinary assertion `FAILED` is recorded and
later steps continue. A failed check is never erased by later success. Add
`on_failure: stop` to an ordinary leaf step when its assertion failure must block
the remainder of that projection. Omission is the only authored default; explicit
values other than the literal `stop` are rejected. This policy is not allowed on
an include-call node and cannot override a child's checks or stopping decision.

This step fragment assumes an earlier `create` response. It checks the result of
a read and explicitly stops after a failed assertion:

```yaml
- id: verify_before_next_action
  on_failure: stop
  do:
    request:
      method: GET
      path: [records, {from_step: create, response_field: id}]
  expect:
    response:
      - check: status_equals
        value: 200
```

| Condition | Outcome and continuation |
| --- | --- |
| Assertion mismatch, default policy | FAILED; later steps may run |
| Assertion mismatch with explicit stop | FAILED; all later leaves BLOCKED |
| Missing/null/unusable referenced response value | Consumer BLOCKED before action; independent later steps may run |
| Execution, normalization, protocol, session, or unknown exception | ERROR; all later leaves BLOCKED |
| Adapter skip or polling SKIP timeout | SKIPPED; all later leaves BLOCKED |

`on_failure` governs assertion failure only. It does not turn a locally blocked
dependency into a global stop. Dependency blocking propagates when another step
needs that blocked step's response. Arbitrary exceptions are not reclassified as
missing values. Ordinary 401/403 responses are not automatically session errors.
Other selected projections still execute independently.

After poll FAIL timeout, later steps may use actual fields from the last response,
with non-final, timed-out provenance. This is not a ready/success response; its
recording remains non-final and cannot satisfy contract's final-only requirement.
Explicit stop still stops on FAIL timeout. No cleanup step is guaranteed to run
after ERROR, SKIPPED, explicit stop, or an unavailable dependency.

See the runnable [Documents continuation example](examples/documents/scenarios/continue_after_failure.yaml)
for creation, checking the list, and deleting by the observed ID. It demonstrates
collecting more checks, not hiding earlier failures or proving that later failures
are causally independent.

A no-check action can be `COMPLETED`; a backend UI-only step is
`NOT_APPLICABLE`. These have empty checks and are not assertion successes.
Projection `PASSED` requires actual checks without failure or degradation.
Any FAILED/ERROR makes the domain/run FAILED. BLOCKED without a failure makes the
domain DEGRADED, even if another check passed, and is visible in `degradations()`.
`EMPTY` and `NOT_SELECTED` cannot satisfy the strict gate.

## Operation inputs and expectation ownership

Core evaluates expectations; operation adapters receive only the prepared inputs
needed by their interface. Request mapping uses `RequestAction` with method,
bound logical path, body, query, and business headers. Browser context creation
receives session and mode/context data; primitive execution receives its permit
and only the business-header names needed for credential-collision checks.
Neither interface receives Scenario, Step, or assertion objects. The UI permit
does not carry the complete resolved-binding map. Core keeps those bindings for
checks and diagnostic reports.

Core-owned operation data is copied independently of declarations and retained
comparison data. A frozen outer object does not make its nested containers
immutable. Authentication/browser handles remain opaque; the explicit mock
queue intentionally shares its cursor across contexts, with an independent
retained fixture plan for validation. Caller-supplied mocks and legitimate
action values may equal expected values; they are not generated from assertions.

The resolver and UI open/action boundary errors identify the failed operation
without reproducing the adapter exception text, which can contain request or
credential data. Existing core comparisons and failure states retain their
meaning. The Python adapter signatures have changed; there is no compatibility
fallback that supplies the former declaration objects. YAML remains unchanged.
These mechanisms reduce accidental coupling and shared-data mutation, not
malicious Python execution or consistently fabricated observations. See the
[evidence trust boundaries](docs/threat-model.md).

## UI evidence and mock sources

Frontend and e2e share one orchestration loop for every step count. Core
authorizes one primitive, checks evidence, resolves later values, and decides
whether the next action may run. Contexts are isolated by current user/session
and closed exactly once. There is no legacy `run_intent()` workflow fallback.

Action identity is separate from traffic: an action may produce zero to many
requests. Each associated request has an immutable ID and response pairing.
Core checks run, step, action, mode, user, session generation, context identity,
permit, and traffic correspondence, then
selects the declared method/path target. With one associated candidate, a wrong
declared query is an ordinary failed request check. With multiple candidates,
an explicit query may select exactly one exact match; no match or multiple
matches remain ambiguous execution errors. Missing or ambiguous target
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
An optional `MockResponse.query` uses decoded wire strings: `None` keeps the
existing method/path fixture scope, an empty mapping requires no parameters,
and a nonempty mapping requires exact equality. Mock routing and core evidence
verification retain the actual query and compare traffic, response, and Recorder
copies; a matching expected query cannot repair different observed traffic.
A locally BLOCKED step issues no permit and consumes no mock. It does not discard
or reorder fixtures: the next real request still has to match the next unconsumed
entry, otherwise the existing protocol error stops execution.

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

Defaulted keyword-only metadata explains continuation without copying values:

- `after_failures` lists earlier FAILED qualified step IDs for subsequent executed
  steps, including assertion-free actions; it does not diagnose causal failures.
- `blocked_by` lists unavailable source IDs or the step that stopped the projection.
- `response_origin` is either absent or a `ResponseOrigin` containing `step_id`,
  zero-based `attempt_index`, `is_final`, `timed_out`, source `user`, and
  `session_generation`.
- Step `user` identifies the effective logical account, or is `None` for anonymous
  execution. Declaration/review views retain the explicit `anonymous` selection.
  `session_generation` records the acquired session (1 onwards; 0 for anonymous);
  unexecuted work has none.
- `binding_sources` maps internal binding names to `BindingSource` objects holding
  `response_field` and the source `ResponseOrigin`. A timed-out, non-final source
  remains distinguishable from a successful polling attempt.

These diagnostic fields do not affect result equality or introduce another
execution gate. They contain source identities, not referenced values; actual
values retain the sensitive `resolved_bindings` boundary below.

Refract does not automatically print or serialize this field. Default step and
nested run representations hide it; provider recordings and sensitive
permit/evidence payloads are also hidden. `sensitive=True` is metadata, not a
security mechanism. `dataclasses.asdict()` and generic third-party serializers
can still expose values. Reports, permits, fixtures, and evidence are sensitive.
This includes `RequestSpec.query`, optional fixture queries, and resolved query
bindings; failure details must not echo query values. Explicit declaration review
can display declared query values and references under its existing source-file
confidentiality rules.
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

Any performed failing check makes the domain and run FAILED, even when its step
also has a tolerated control-flow outcome. In particular, polling with
`on_timeout: SKIP` still blocks later steps, but cannot hide an actual request-header
mismatch observed during an attempt. A response-readiness timeout alone retains
the existing SKIPPED step and DEGRADED aggregate.

## Contract identity

Contract consumes backend recordings without sending requests. Its identity is
`(step_id, method, declared template_path)`; bound and actual paths remain
evidence, not replacements for declared identity. Verified query remains
evidence; runtime query values do not become endpoint identities.
Contract is response compatibility over those recordings,
not a second query sender or an independent query witness. Query-only bindings
do not create response assertions or new endpoint identities. As with path and
header bindings, an executed consumer still requires available source values
valid for their declared use; impossible dependencies are errors, while verified
unexecuted consumers remain BLOCKED. Core-controlled user/session metadata must agree with the declaration;
another user's recording cannot
substitute for the declared user. Contract does not authenticate or independently
prove account identity. Runner supplies backend execution metadata to check each recording's
actual session generation. A direct contract call without that provenance cannot
verify a flow with `session: new`; it reports an error instead of inferring which
renewal steps actually ran. Validated execution metadata also retains unexecuted
BLOCKED consumers as BLOCKED rather than inventing a missing-endpoint failure.
Missing or contradictory execution metadata does not justify omitting checks.
Errors in one consumer's response dependencies do not erase checks on independent
endpoints. Without execution metadata, missing provider evidence remains
fail-closed. Only final polling recordings
contribute. Response requirements retain success/failure/don't-care, an optional
exact HTTP status or allowed status set, required
fields, all complete field-equality and field-inequality constraints, forbidden fields, selected response-header equality or
absence, all numeric/list-length bounds, and all collection matching constraints.
Header checks use the complete
raw response pair list captured before normalization; missing or ambiguous
header evidence is an error, not proof of absence. Headers do not change endpoint
identity or make contract an independent observer. Field comparisons retain both
checks on the same field and use actual provider-reference values, including
complete objects/lists and nested declared references. Missing or invalid
evidence cannot pass inequality. Contract uses the same strict comparison as
runtime and does not reduce these requirements to field presence. Numeric and
length bounds retain every operator and resolve thresholds from provider
observations; unavailable or invalid thresholds cannot pass. Collection checks evaluate final provider collections with the
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
users: [editor]
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
