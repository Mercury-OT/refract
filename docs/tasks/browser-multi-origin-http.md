# Bounded multi-origin browser HTTP support

Status: scope approved; implementation and independent review authorized on
2026-10-30. The maintainer also authorized submission after successful independent
audit and architect acceptance, followed by PR/main checks and branch cleanup.
Starting main: `3a0b1a5`. No Scenario expression changes are authorized.
Local architect acceptance subsequently passed; see the
[measured results and audit record](browser-multi-origin-http-acceptance.md).

## Purpose and source boundary

Support a page, finite HTTP APIs and static assets hosted at different explicitly
configured origins. Product adapters keep target/rendering mappings; the optional
browser package owns collection. Sources are the existing public browser helper,
its synthetic HTTP tests, and a new neutral records example. No external use-case
corpus, private integration, or adoption measurements are inputs to public files.

This is capability and cost evidence for a bounded integration, not universal
browser compatibility, independent proof of an adapter's truth, or measured human
review savings. Format 1, one-level inclusion, assertion vocabulary, business
values and the strict `status == PASSED` gate remain unchanged.

## Configuration and ownership

The existing single-origin helper remains available. Multi-origin behavior is
explicitly enabled with `BrowserSupport(..., network_policy=policy)`.

`BrowserNetworkPolicy` contains:

- `api_endpoints`: immutable `ApiEndpoint(origin, path_prefix, logical_prefix)`
  entries. Each maps one actual path prefix at an exact origin to one logical
  path prefix. Prefixes are segment-bounded, not substring replacements. Actual
  and logical prefix ownership must not overlap ambiguously; an empty logical
  prefix owns the whole logical space. The old `logical_path` callback cannot
  also be supplied in this mode.
- `resource_origins`: origins allowed to serve GET/HEAD documents and static
  resources. The page origin is included. This does not authorize fetch/XHR API
  evidence, unsupported transports, or credential delivery.
- `credential_origins`: origins allowed to receive browser-native Cookie,
  Authorization and Proxy-Authorization headers.
- `credential_headers`: additional lowercase credential header names mapped to
  their allowed origins. Context extra-header names are credential-bearing too;
  an undeclared destination must fail before send, not silently strip credentials.

Origins are canonical HTTP(S) scheme/host/effective-port identities; no wildcard,
userinfo, path, query or fragment rules. Invalid or ambiguous configuration fails
before context/action. Credentials are supplied through the existing authenticator
and browser storage. The helper does not inject or repair authentication. Native
cookies still obey browser rules, with the policy acting as an additional delivery
restriction. Unsupported proxy, HTTP-auth and client-certificate configurations
are rejected in this bounded mode rather than claiming untested delivery controls.

Resource permissions, credential permissions and API evidence permissions are
separate. Unknown destinations fail before HTTP delivery. Same-path requests at
different configured API origins remain distinguishable through explicit logical
prefix ownership and preserved actual origin. No observed response or assertion
chooses a mapping. The policy cannot receive Scenario, Step or expectations.

## Native request collection

The opt-in path uses Chromium's actual request/response lifecycle, not a second
HTTP client. Browser-level interception guards the first request from secondary
targets before delivery; only the primary page/frame can contribute evidence.
Closing a popup after its request was sent is not sufficient. Per-request
computed JavaScript method names carry local association
identities in native initiator stacks; they require neither eval nor wire headers.
The request's browser network ID connects that initiation to interception and
completion. URL equality, response content, request order and temporal proximity
cannot establish action association. Native async/await continuations and timers
retain the existing unassociated/diagnostic behavior.

The browser performs CORS and preflight. Simple requests must not gain preflights
from Refract markers. Application-authored preflights remain effective. Neither
web security nor CORS response headers may be changed to obtain a pass. Only a
successfully completed, browser-readable response becomes response evidence;
browser denial or incomplete acquisition cannot expose a successful response.
Actual request headers, response headers, query, ordinary JSON/form bodies and
response data are captured, with the existing supported-shape rules. No automatic
redirect following, API replay, business-value substitution or response repair.
Explicit `no-cors` fetch mode is rejected, not used to expose an opaque response
through the debugger. Associated fetch responses are passively drained through a
clone so the application need not consume the body; its original response is not
replaced. Native response capture is limited to 8 MiB and the existing deadline;
exceeding the limit is an error, not a partial successful response.

Static traffic may proceed without becoming request evidence. Finite background
HTTP at configured endpoints remains diagnostic, even when it matches a declared
request. Completion waits only for associated work. Native diagnostics are bounded
to 100 records and 256 KiB of complete serialized records per context, including
request values and headers; overflow is visibly reported, not silently discarded.
This bounds retained diagnostics, not all browser memory. No streaming bodies
are read to manufacture a finite response.

## Minimal evidence metadata

Add a frozen `BrowserNetworkIdentity(origin, request_id)` port value. Optional
keyword-only `browser_identity` fields on `UiTraffic` and `RecordedResponse`
carry independently retained copies of this actual origin/network identity.
They are sensitive and omitted from default representations. Core checks type,
canonical origin, nonempty network identity, pair equality and replay within the
current browser context, in addition to all existing permit/user/session/request
checks. Recorder and normalization ownership tests cover these fields.

Native collection does not invent a transmitted trace. In this explicitly marked
branch only, request traceparent and response trace ID may both be absent. A
present trace must satisfy existing pairing and replay rules and correspond to
observed request headers. Unmarked evidence retains its existing mandatory trace
rule. Native request identity is not proof of server trace participation. Declared
trace-dependent state evidence must remain visibly unavailable/failing without
a real trace; no local browser identity is passed off as a server trace.

`UiActionEvidence.diagnostic_notes` is an optional keyword-only list of safe
diagnostic notes, copied into step `not_checked`; it does not change pass/fail or
remove a required check. The only notices are `background diagnostics truncated`
and `background HTTP acquisition failed`, each appearing at most once. Ordinary
unassociated connection failures retain a note rather than failing an unrelated
action; policy violations and CORS denials remain errors. This channel must not
expose payloads or credentials.

## Mock and failure boundaries

Mock API requests consume the existing explicit shared fixture queue and never
fall through to live API endpoints. The policy gives each logical prefix one
source, preventing fixture consumption by a different service. Any cross-origin
CORS/preflight response required in mock mode must be explicitly supplied, not
fabricated from expected assertions. An unsupported preflight can fail closed;
it cannot be fulfilled with permissive inferred CORS headers. Native fulfilled
mocks have no complete raw response-header block in this slice; that evidence
remains unavailable and header-dependent checks cannot pass using authored
fixture headers as a substitute. Static GET/HEAD resources retain their
explicitly allowed network behavior.

Unexpected origins, redirects, credential delivery violations, malformed or
ambiguous evidence, and incomplete associated acquisition cause visible errors.
Native CORS denial remains failure; a page opening is not a successful business
check. Normal business refusals still pass when the approved assertions expect
them. Existing anonymous/session/continuation and cleanup rules remain.

## Fixed consumer and cost panel

Use one public synthetic records application with two independently written UI
request paths: supported registered-Promise callbacks and native async callbacks.
The same ten files and obligations are used for both implementations:

| ID | Obligation |
| --- | --- |
| c01 | Page and independently hosted static asset are visibly ready. |
| c02 | Public list contains the expected records. |
| c03 | A category query reaches the server unchanged and filters the result. |
| c04 | The next page uses the declared pagination and contains different items. |
| c05 | Fill and create a record with a run-unique code. |
| c06 | Read a newly created record by its observed string ID. |
| c07 | Change a created record and read the changed content. |
| c08 | Delete a created record and observe its absence from the API list. |
| c09 | An anonymous protected write is refused. |
| c10 | A named user can perform a protected read. |

Fixed controls accept entered string IDs; no new dynamic target or hidden adapter
action is needed. Native-async request cases retain missing-association failures,
not changed expectations. All 20 units stay in the results. Existing baseline
`3a0b1a5` is executed with the same application/Scenario obligations and its legacy
helper configuration; baseline rejection is recorded, not inferred.

Report per-unit status, actual command/elapsed time, independent server requests,
Scenario hashes and stable source versions. Count Python nonblank/noncomment
lines separately for product adapter, reusable collection, target application,
tests/harness; count mapping entries and YAML lines separately. Human writing,
diagnosis and review time is unmeasured unless actually tracked. Run one fixed
selector/endpoint-prefix maintenance variant with unchanged Scenario hashes.
No LOC threshold substitutes for correctness and no blocked case is dropped.
Shared browser test helpers use the existing production-default 5000 ms budget;
explicit short-deadline tests retain their authored budgets. This is not a change
to production deadlines or removal of timeout coverage.

## Acceptance matrix

1. Existing single-origin live/mock, query/header checks, single-action, anonymous,
   multi-user/session, replay/stale and missing-evidence tests remain green.
2. Configured cross-origin APIs and resources work; unlisted destinations receive
   no HTTP request. Same path at different sources cannot be confused.
3. Independent server observations prove credential destinations, actual request
   values/counts, and absence of private markers or injected trace headers.
4. Simple CORS, application-authored preflight, and denied CORS/preflight remain
   distinct. No hidden replay or permissive CORS repair.
5. Identical-path background, delayed previous response, and continuous background
   do not satisfy current evidence or require global network idle.
6. Missing/wrong mocks cannot reach live API services. Explicit mocks cannot
   fabricate live evidence or bypass source/CORS restrictions.
7. Origin/network metadata, absent/present traces, pair/replay checks, recorder
   mutation, incomplete headers/body and default-repr privacy have negative tests.
8. Diagnostics are bounded and truncation visible; contexts/connections close on
   success and error. Unsupported streams/workers/redirects remain explicit.
9. The fixed consumer panel and maintenance variant retain every blocked result.
10. Full tests, fresh dev-only Python 3.11/3.12, core litmus, documentation/boundary
    sentinels, lock check, hygiene and diff checks pass. Core never imports the
    browser package or adapters. Existing YAML/vocabulary stay unchanged.

If native source association, credential delivery or unchanged CORS cannot be
established, deliver a bounded blocker with evidence. Do not guess, patch the
target, weaken assertions, broaden transport scope or claim full compatibility.

## Non-goals and delivery

No WebSocket, SSE, worker/service-worker, generalized authentication redirects,
popup/frame flows, native async attribution expansion, new actions, dynamic UI
targets, Flow, workbench, database feature, new report status or declaration term.
No access to local private projects or evidence. Public source review precedes
submission; the independent audit must not be performed by the implementer.
Deliver this specification, code/tests, browser guide, fixed panel/cost results,
acceptance record and a short maintainer summary. Update only relevant roadmap
delivery index facts; do not rewrite historical acceptance records.
