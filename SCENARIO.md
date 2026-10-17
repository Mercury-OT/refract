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
| `parameters` | no | mapping of declared data values |
| `grid` | no | organizational selector `{level, module}` |
| `steps` | yes | nonempty ordered list with unique step IDs |
| `results` | no | named aliases of this Scenario's own observed response fields |

Parameters contain finite JSON-like data, not scripts or generators. Unknown
fields, duplicate mapping keys, and invalid reference shapes fail validation.
A requested grid filter does not silently match a Scenario without that grid.

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
`field_equals`, `field_not_equals`, or `collection_matching_count` on the same
field, are invalid.

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
binding aliases, expressions, arithmetic, concatenation, JSONPath, reference-valued
mapping keys, or coercion are supported. Frontend references read mock responses,
which remain distinguishable from live responses.

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
invocation has isolated parameters and steps; literal objects resembling reference
syntax remain data. No additional parameterized positions are introduced.

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
do not create response requirements or prevent evaluation of declared response
checks. Core-controlled user/session metadata must agree with the declaration;
another user's recording cannot
substitute for the declared user. Contract does not authenticate or independently
prove account identity. Runner supplies backend execution metadata to check each recording's
actual session generation. A direct contract call without that provenance cannot
verify a flow with `session: new`; it reports an error instead of inferring which
renewal steps actually ran. Only final polling recordings
contribute. Response requirements retain success/failure/don't-care, an optional
exact HTTP status or allowed status set, required
fields, all complete field-equality and field-inequality constraints, forbidden fields, selected response-header equality or
absence, and all collection matching constraints. Header checks use the complete
raw response pair list captured before normalization; missing or ambiguous
header evidence is an error, not proof of absence. Headers do not change endpoint
identity or make contract an independent observer. Field comparisons retain both
checks on the same field and use actual provider-reference values, including
complete objects/lists and nested declared references. Missing or invalid
evidence cannot pass inequality. Contract uses the same strict comparison as
runtime and does not reduce these requirements to field presence. Collection checks evaluate final provider collections with the
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
