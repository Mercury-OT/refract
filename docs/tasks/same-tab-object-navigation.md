# Same-tab navigation after object selection

Status: maintainer approved feasibility-first delivery on 2026-10-31, starting
main `f77450f`. After reliable association is demonstrated, specification,
development, independent audit and architect acceptance precede the authorized
submission, green PR checks, merge, green main checks and branch cleanup.

## Purpose and unchanged contract

An observed object's control may open its detail/editor as a new HTML document
in the same tab and origin. Subsequent explicit steps continue in that user's
existing browser context. This supersedes only the full-document limitation in
the preceding object-selection task; it does not revise its historical evidence.

Keep schema_version: 1, current YAML, one-level inclusion, all core ports and
assertion vocabulary. The existing click target/object_id identifies the control
and object. Navigation is an observed consequence, not another action. There is
exactly one real click, no repair request, synthetic click or substitute goto.
No existing product or private workspace is accessed or changed. Object absence
and Flow remain deferred. No new dependency, general mapping language or report
state is introduced. R1 is unchanged.

## Feasibility gate

Two separate real-Chromium probes established that CDP Runtime binding events
retain an old document's actual trusted-click receipt before document teardown,
including its execution-context identity. Native Navigation API observations
distinguish a trusted anchor's default navigation from script navigation. CDP
main-frame, document request, loader and commit events provide the transition
chain; URL equality alone does not establish causality.

Negative probes established important restrictions: script navigation does not
set userInitiated; a synthetic anchor clicked inside a real callback can inherit
a script stack; two location assignments can emit two document requests but
only one navigation event; and Promise callbacks can run before eventPhase is
reset. Therefore eventPhase, time windows, stack presence, and destination URLs
are insufficient proofs by themselves. Retained regression tests, not these
exploratory observations alone, are required before acceptance.

## Bounded association and receipt ownership

Support two forms for object-scoped clicks:

1. Default navigation of the exact pinned anchor control, including a click on
   its descendant. The native navigate event must identify that anchor as
   sourceElement and be user initiated.
2. A synchronous location assignment in the accepted click's actual handler.
   A separate invocation scope surrounds only synchronous event callbacks, not
   Promise/await/timer callbacks. The navigation observation must have no source
   element and match that scope and the current action origin. Synthetic nested
   events establish an unassociated scope and cannot borrow the outer action.

The helper retains an owned copy of the actual unique row/control selection at
trusted dispatch, before product handlers. Bind it on the host to the active
permit, execution, user, session generation, browser context, main frame, source
document loader and default-world unique execution context. Browser payloads
cannot select another permit or resurrect a completed action. Unknown, reused,
wrong-frame, stale, duplicate or new-document receipt sources fail visibly.
Do not reconstruct the receipt from the requested ID or destination page.

Require one supported old-document navigation observation, one current-tab
main-frame request and one matching committed loader. The method is GET and the
origin is exactly the existing page origin (scheme, host and port); broader
same-site navigation is not implied. A normal successful HTML document must
load within the existing action deadline. Redirects, downloads, error documents,
multiple competing requests/commits and missing proof fail. URL comparison is
only an integrity check within that established chain, never an association key.

Retain old-document instrumentation errors and outstanding action-work facts
through unload. A pending old-document promise/request or error cannot disappear
when the new document initializes. This first slice rejects such incomplete
work rather than broadening asynchronous navigation. New-document state starts
unarmed. Its startup requests remain diagnostic/background; a document GET does
not become an API response or satisfy a declared API expectation. Existing
legacy/native transport, strict mock queues, credential, replay, deadline and
cleanup rules remain in force. Unsupported navigation returns existing ERROR
and closes the unusable context; it cannot produce PASSED/degradation fallback.

## Evidence and threat boundary

Selection proves which observed control was clicked; it does not prove the
destination displays the right object. Scenarios must use existing UI or later
explicit response checks for that obligation. A deliberately wrong destination
must fail those checks in the consumer, even with a correct selection receipt.
No request is sent to repair a wrong destination.

This protects against accidental stale evidence, background attribution and
mapping mistakes in cooperative browser/adapter code. It is not attestation
against hostile code in the same process or page, nor independent evidence merely
because several browser APIs describe the same action. Browser callbacks receive
no expectations. Default repr and errors omit URLs, IDs, credentials and payloads.

Non-goals: asynchronous location changes, timer navigation, cross-origin pages,
redirect/login flows, tabs/popups, frames, form submission (including GET forms),
POST documents, download observation, native application drivers and arbitrary
browser compatibility. Existing same-document behavior remains unchanged.

## Acceptance matrix

| Obligation | Required evidence |
| --- | --- |
| Retained actual selection | Real anchor and synchronous-handler navigation in legacy/native live and mock modes; one actual click; source receipt survives unload. |
| Follow-up operation | New neutral frozen HTML consumer: API create, open list, scoped click, fill, save, explicit API read; existing user/session reused and decoys unchanged. |
| Source isolation | Wrong frame/world/document, stale action, duplicate receipt and new-document replay rejected; receipt values remain actual observations. |
| Causality | Timer, Promise/await navigation, synthetic anchor, synthetic nested handler and competing document requests cannot claim supported association. |
| Completion | Old error or unfinished action work, aborted/failed/redirected navigation, deadline and missing receipt cannot pass; close is idempotent. |
| Transport separation | New-page bootstrap API is not click traffic in live or mock; missing mock never falls through to a live API; next explicit action retains normal association. |
| Integrity | Existing missing/duplicate/changed object selection controls stay red; wrong destination UI identity and wrong subsequent save are detected. |
| Compatibility | Core/loader/vocabulary/existing YAML and previous frozen target bytes unchanged; related browser, lifecycle, users, native-await, full suite and hygiene pass. |

Create new neutral targets before writing their mappings/tests and freeze their
source hashes. Use two small navigation forms; a shared synthetic server is
allowed and disclosed. Separate faulty target variants are explicit controls,
not edits to normal targets. This demonstrates mechanism and interoperability,
not broad product adoption or quantified maintenance savings.

Independent audit must challenge source/loader association and at least one
actual background/synthetic negative, not rely only on developer test counts.
Delivery records contain actual commands, results, limitations and information-
source review. Public sources are current public code, official protocol behavior
and newly authored synthetic fixtures only; no private source or evidence enters
the repository.
