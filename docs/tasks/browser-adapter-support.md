# Browser adapter support

Priority and delivery state are maintained in the [roadmap](../roadmap.md).
This task uses the public Demo adapter and independently authored synthetic
pages. Its implementation, examples, tests, and documentation must not include
non-public product code, mappings, measurements, names, paths, or evidence.

## Scope and unchanged boundaries

Provide optional, reusable Playwright support for browser lifetime, one declared
primitive at a time, request and response collection, bounded readiness waits,
and cleanup. Migrate the public Demo UI adapter to use that support so reuse is
demonstrated by executable code rather than a second unused implementation.

Do not change Scenario YAML, declarations, assertions, reports, runner behavior,
or the existing ports. Existing files under `refracto/`, existing Scenario YAML,
and the Demo application stay unchanged. Product adapters still own page and
element mappings, authentication, rendered-field interpretation, and response
normalization. They must not hide a business flow inside one primitive. No
authoring UI, general browser automation framework, report export, or new
business assertions belong in this task.

Ship support in the separate `refracto_browser` package in the same distribution,
with a `browser` optional extra. Core imports and its offline test suite must
continue to work without Playwright. Existing Demo dependencies and tests remain
usable. No stage, commit, push, branch, PR, or merge is authorized.

## Support interface

Use one public `BrowserSupport` helper, without adding another core port:

- Construction accepts `base_url`, a product-owned read-only `read_rendered(page)`
  callback, an optional `logical_path(actual_path)` mapping, and a positive finite
  timeout in milliseconds. The default logical path removes one leading slash.
- `open(mode, mock_plan=None, context_options=None)` creates an owned browser
  context and page, installs collection before application scripts, and returns
  an opaque context initially at `about:blank`. It does not navigate, login, seed
  business objects, or execute a Scenario. The product adapter may supply its
  authenticated browser context options; sensitive values must not be printed.
- `perform(context, permit, *, url=None, selector=None)` executes exactly one
  permitted `open`, `click`, or `fill` and returns the existing `UiActionResult`.
  An open uses an explicit same-origin URL; click and fill use one CSS selector
  for a uniquely visible element. Fill requires a string, without coercion.
  Values and selectors come from the adapter, not from inspecting expectations.
- `snapshot(context)` delegates read-only rendering to the supplied callback.
  Core continues to own wait actions and sequence/stop decisions.
- `close(context)` releases all owned resources, including partially opened
  resources after a failure. Repeated close is safe; use after close is rejected.

Reject incompatible argument combinations, invalid modes/timeouts, reused action
authorization, and cross-run/context permit mixing. A context binds to one
execution ID. Do not retain Scenario objects or derive mock responses from
expected values. Keep implementation types and browser handles out of repr.

## Action readiness and completion

Wait within a bounded deadline for the declared target to become visible, then
require exactly one visible match before acting. Zero or multiple matches must
not select an arbitrary first element. Passive waiting may not add clicks,
keypresses, navigation, API requests, or retries of the business action.

Wait for supported requests causally associated with the current action to
finish response collection, including delayed bodies, before returning evidence.
Do not use global network idleness as proof of completion or request ownership.
Continuous unrelated traffic must not prevent a completed action from returning.
Use bounded rendering completion opportunities, not assertions as wait predicates.

A declared request that is absent still fails under the existing core rules.
Collection timeout, transport failure, unsupported evidence, target ambiguity,
and cleanup failure must remain visible errors, never fabricated empty successful
responses. Keep the current core ERROR and subsequent BLOCKED behavior.

## Supported request association

Support same-origin fetch and asynchronous XMLHttpRequest originating in a
targeted DOM event handler. Explicit Promise callbacks registered in that
tracked chain may inherit its origin. Native async/await continuations, timer
callbacks, workers, service workers, frames, streaming bodies, navigation-driven
API work, and other untracked sources are not promised as associated evidence.
Untracked requests remain diagnostics, even when their method/path matches the
declared request. Unsupported transport forms fail visibly when needed.

Origin must be captured where the request starts, not reconstructed from its
arrival time, current active step, expected method/path, response contents, or
position in a list. Multiple requests from an action retain distinct request IDs;
core selects and validates the declared one. Delayed responses from a prior
action cannot be relabeled as belonging to the next action. Preserve listener
registration/removal behavior and reset origin in finally blocks after errors.

Use the existing UiActionPermit, UiTraffic, UiActionEvidence, RecordedResponse,
and RequestSpec shapes. Pair responses with their actual requests and preserve
body, response status/content, trace and request identifiers truthfully. Do not
repair wrong traffic by sending an independent API action. Internal association
markers must not be sent to the application server; trace headers retain their
documented local-correlation meaning. Cross-origin traffic is rejected in this
bounded helper. Do not forward credentials through an unvalidated redirect.

This is instrumentation inside the tested browser, not independent protection
against a malicious application, adapter, or normalizer. Unsupported async
origins must not acquire an origin merely because the helper waits longer.

## Live and mock behavior

Live mode records the real request and response without substituting expected
data. Preserve the existing public Demo backend-state trace behavior.

Mock mode consumes the caller's explicit ordered MockResponse plan, including
background requests. Preserve fixture IDs and consumption reporting. Missing,
wrong-order, or mismatched fixtures abort and never fall through to a live API.
Repeated endpoints may consume different fixtures. Missing/unassigned origins
are diagnostics in either mode, not an excuse to invent a step association.
The same helper must not confuse mock response evidence with live evidence.

## Data and failure handling

Keep request bodies, response bodies, browser context options, authorization
tokens, bound values, and element input values out of new default repr and
human-readable error strings. Do not print URLs with secret query values or
underlying Playwright exception messages containing selectors or input data.
Retained raw port objects remain sensitive; this task does not authorize a
generic serializer or promise universal redaction.

Route handlers and instrumented event listeners must be cleaned up with their
context. Errors during browser launch, context/page creation, navigation,
interaction, response collection, rendering, or close cannot strand owned
browser resources. Do not terminate unrelated browsers or processes.

## Required acceptance evidence

1. A public synthetic adapter and unchanged Demo use the helper through existing
   ports. Real Chromium tests run without skips in the full environment. Core
   remains importable/testable with only its dev extra.
2. Real fetch and XHR actions each produce correctly paired requests/responses;
   delay a response body beyond the handler return and prove it is collected.
   Cover more than one request per action and repeated endpoints across steps.
3. An explicitly registered Promise callback retains a supported origin. A timer
   or untracked continuation, including identical method/path traffic, cannot
   satisfy a declared request. Test background traffic during successful work.
4. Delayed previous-action responses, mixed execution IDs and reused permits
   are rejected or left unassigned, never used as current evidence. Exercise
   event listener removal and thrown-handler cleanup.
5. A target appearing after a short delay is handled by passive waiting; absent
   and duplicate visible targets fail without any action. Verify action counts
   and no implicit navigation on open/context creation.
6. Transport aborts, never-finishing responses, mapper/render failures and
   closed contexts fail visibly. Core-level integration shows ERROR/BLOCKED and
   verifies no later action is performed. Cleanup paths release owned resources.
7. Mock fixtures with repeated endpoints remain ordered; unplanned requests never
   reach the backend. Existing frontend/e2e Demo tests remain strict PASSED with
   no degradation. Live tests use an actual local HTTP server, not only mocks.
8. Sensitive sentinels do not appear in new object repr, exception strings or
   report default repr. Verify internal markers do not reach the server and
   cross-origin/redirect rejection does not forward secret headers.
9. Package-install smoke checks prove the helper is shipped and optional. Full
   regression, declaration validation of maintained YAML, lock consistency,
   repository hygiene, unstaged/cached diff checks, and a separate core-only
   environment pass. Review untracked files as well as tracked diff for neutral
   information sources; do not add a private-name denylist.

Public guidance must show how an adapter supplies element/URL mappings and a
read-only rendering callback, and explain supported origins, timeouts, explicit
mock plans and limitations. Tests must demonstrate behavior and negative cases;
test quantity alone is not acceptance. Independent audit precedes architect
acceptance, and neither authorizes submission.
