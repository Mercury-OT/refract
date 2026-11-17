# Bounded background HTTP compatibility

Status: development, independent audit and architect acceptance passed on
2026-11-17; see the [verification record](browser-background-http-compatibility-acceptance.md).
The maintainer accepted delivery and separately authorized task-branch submission
and merge after required checks on 2026-11-17. Publication, main CI and cleanup
are evidenced by the associated PR and main history. Starting main: `29b5e10`.

## Purpose and source boundary

Allow normal resource loading through XHR/Fetch and live background API requests
with JSON-array bodies without mistaking them for declared action evidence.
The public implementation and tests use synthetic pages, assets and records.
No private product, workroom information, local credentials, paths or raw run
artifacts enter public files. This is a browser-helper compatibility repair,
not a business acceptance result or a promise of universal page support.

Format 1, the existing YAML structure, one-level inclusion, declaration
vocabulary, RequestSpec body types and all business checks remain unchanged.
No product modifications, new UI actions, downloads, WebSocket, EventSource,
worker/service-worker, redirect or frame expansion are included.

## Explicit resource routes

Add exported immutable `ResourceRoute(origin, path_prefix)` and optional
`BrowserNetworkPolicy.resource_routes`, preserving existing positional fields.
Origins and prefixes use the existing canonical validation. The root prefix is
not allowed: routes must identify a bounded resource path. Duplicate/overlapping
resource routes at the same origin and resource/API prefix overlap are rejected.
At bind time a route origin must already be the page origin or an explicitly
allowed `resource_origins` entry. A resource route cannot independently grant
origin or credential permission.

A matching XHR or Fetch GET/HEAD is classified as a resource (`logical=None`).
It may reach the server and browser but cannot produce RequestSpec, UiTraffic or
contract evidence. Existing static stylesheet/script loading remains unchanged.
POST, OPTIONS and preflight receive no new resource permission. Unknown paths,
origins, credentials, redirects and unsupported transports remain fail-closed.
Credential checks run before the resource exception. API/resource ambiguity must
fail configuration validation, not be resolved by response content or ordering.

## Live background array bodies

Native request ownership is established from the existing direct marker or
bounded invocation ancestry before interception. Only `mode == live` and an
unassociated request (`action is None`) may use this exception. Only valid JSON
arrays at an already configured API destination are newly tolerated. Existing
header, trace, query, file-selection and destination checks still apply.

Chromium sends the original request bytes. Do not wrap the array, coerce values,
replace it with an empty object, replay it with another client, or construct a
RequestSpec whose body violates its existing `dict | None` contract. Scalars,
non-JSON bodies and unsupported multipart formats receive no new permission.
Associated unsupported bodies still fail; endpoint equality or timing can never
turn background traffic into the expected request.

An array request has no complete typed diagnostic recording. Mark it explicitly
with the fixed safe note `background request body not represented`, once per
context. Do not retrieve a response body to create an invalid recording. Keep
only existing in-flight transport metadata until completion/failure, then retire
it; do not introduce an unbounded secondary log. The note describes missing
optional diagnostics, not a successful business check or an acquisition failure.
Existing CORS denial, policy failure, response streaming/redirect restrictions,
transport failure notes and collection deadlines retain their semantics.

Core's diagnostic-note whitelist gains exactly this fixed note, with a maximum
of three distinct existing/new notes; unknown notes and duplicates still fail.
No report status or arbitrary error text is introduced. The note propagates into
existing `not_checked`; it does not waive any declared assertion. Existing
object-shaped background diagnostic capture and its byte/work limits remain.

## Mock and evidence boundaries

The new array transport exception is live-only. Unsupported array requests in
mock mode must not reach the API service or consume an ordered fixture. Existing
object-shaped mock handling remains unchanged. Explicit static resource routes
may load real GET/HEAD assets just like existing static resources; they are not
API fixture destinations and cannot overlap API routes.

All existing primary evidence identity, user/session, permit, trace, query,
header and body checks remain. Missing primary evidence must remain an error or
blocked result. A background request to the expected endpoint cannot rescue it.
The cooperative threat model remains: guards prevent accidental misassociation
and unsafe configuration, not adversarial code in the same host process.

## Acceptance matrix

1. Policy tests reject root/invalid/duplicate/overlapping routes, API overlap,
   undeclared resource origins, disallowed methods and credential destinations.
   Existing positional policy construction remains compatible.
2. Independent synthetic server receipts verify identical CSS bytes loaded via
   XHR and Fetch GET/HEAD on an explicit route; ordinary stylesheet works too.
   Unconfigured siblings and origins receive no request. No primary/typed API
   diagnostic record is invented for assets.
3. Independent server receipts verify unchanged array request bytes and normal
   response delivery for background Fetch and XHR. The omission note is visible,
   no invalid RequestSpec/UiTraffic/contract recording is created, completion
   retires entries and does not perform optional response-body reads.
4. Direct and native-await associated arrays fail, with no delivery or fallback.
   Background same-endpoint arrays cannot satisfy missing primary evidence.
   Mock arrays fail without live API delivery or fixture consumption.
5. Object-background capture, credentials, query/trace validation, CORS denial,
   redirects, streaming, file-selection boundaries, diagnostic budget/cleanup,
   and missing-evidence checks retain meaningful positive/negative coverage.
6. Core accepts only the three fixed unique notes and preserves strict business
   outcomes. Sensitive payload/credential values are absent from the new note.
7. Re-run the frozen public-product page openings externally on an unchanged
   build with only the explicit resource policy added. Record actual HTTP
   progress and any later blocker. Do not disable a product transport or claim
   page business acceptance without running its approved business Scenarios.
8. Full tests, fresh dev-only core checks, litmus, lock, repository hygiene and
   diff checks pass. Public changes remain unstaged until separate authorization.

## Delivery and stopping rule

Deliver this specification, bounded helper/core-note changes, synthetic tests,
updated browser guide, an acceptance record and the relevant roadmap status.
Raw actual-target evidence stays local outside both repositories. Previously
frozen evidence is preserved. Independent audit is performed by a different
agent from implementation. If ownership, byte preservation or credential checks
cannot be kept reliable, stop and report the blocker rather than weaken checks.
A later non-HTTP blocker requires its own reviewed scope; it is not permission
to extend this repair. The download task remains paused.
