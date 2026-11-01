# Enter-triggered same-page form submission

Status: maintainer approved the scope and evidence boundary on 2026-11-01,
starting main `b6107be`. First establish reliable association in real Chromium;
only then implement, independently audit and accept the change. The maintainer
also authorized subsequent task-branch submission, green PR checks, merge,
green main checks and branch cleanup after acceptance. No private workspace or
existing product is accessed or changed.
Development, both independent audits and architect acceptance subsequently
passed; see the [verification record](enter-form-submission-acceptance.md).

## Purpose and unchanged declaration

Support an already-focused text/search input whose native Enter default action
submits its owning form, where the application's submit handler cancels native
navigation and sends a finite fetch/XHR request. This is different from a key
handler sending the request directly, which is already supported.

Keep schema_version: 1, existing metadata/parameters/steps/expect, one action per
leaf, one-level inclusion, users/sessions, assertion vocabulary and result states.
The existing do: press / target / key: Enter expression is unchanged. No submit
action, configuration field, expectation or key is added. An implicit native
button activation belongs to the single Enter operation; the helper must not
click a button or call a form-submission method to complete it.

Reuse the approved search Scenario unchanged on a separate, frozen neutral
form-based target. Its request, response and UI checks retain their existing
meaning. The adapter receives only operation inputs, maps logical elements and
reads actual rendering. It must not inspect expectations, insert a handler,
modify product behavior, repair focus or send a replacement API request.

## Feasibility gate

Before repository implementation, probe real browser event ordering and both
supported transport branches. Demonstrate a bounded chain from the pinned,
already-focused input through its actual owning form and native submitter to
the submit callback and its observed request. Establish which submitter shapes
are supported rather than infer arbitrary forms from a passing example.

The event's isTrusted flag alone is insufficient: programmatic requestSubmit
can generate a trusted submit event. Neither a matching URL, query, response,
user-activation flag nor temporal proximity proves this Enter caused a request.
Challenge requestSubmit, submit, programmatic click/dispatch, nested callbacks,
wrong forms, changed form ownership/submitter, background work and stale events.
An unsupported path stays unassociated or fails visibly; it cannot satisfy the
declared request. If no bounded reliable route exists, report that result and
stop rather than removing the guard or weakening the expectation.

Listener, property and delegated submit handlers require actual checks. Reuse
existing bounded Promise and native-await ancestry only where demonstrated;
timers, independently scheduled work and unsupported ancestry remain diagnostic.
Same-path background traffic must not rescue an absent action request.

Gate result, 2026-11-01: a 36-case scratch Chromium matrix passed before helper
implementation. Native event ordering was observed as keydown, keypress, default
submitter click, submit, keyup. The bounded route pins the input/form and actual
first form-owned native submitter, admits that native chain and establishes null
invocation scopes around programmatic submissions. Both button type=submit and
input type=submit, including an externally form-associated button, were observed.
No-default-submitter and image-submitter forms are outside this proven route.
Additional transport/mock/validation checks remain part of implementation tests.
The final pre-implementation gate passed 41 cases in 37.30 seconds, including
native/legacy XHR, explicit mocks and browser validation. Retained regression
tests replace the scratch candidate as the reproducible implementation check.

## Browser and evidence contract

Retain the current unique, visible, enabled, editable main-document text/search
input boundary and one observed Enter down/up pair. The exact input must already
be focused. Form support does not authorize focus repair, input replacement,
changing validation, forcing submission or preventing product validation.
Revalidate identity and form ownership at the actual event boundary. Focus theft
remains an error even if focus later returns. Errors cannot undo effects already
produced before detection.

Only the validated native activation/submission chain may acquire this action's
origin. Programmatic and synthetic submissions establish an unassociated scope,
including inside a genuine keyboard or submit callback. An unrelated callback
must not inherit that origin through property handlers or async continuation.
Do not disable normal application events merely to manufacture passing evidence.
The implicit submit-button click is transition evidence only: requests from its
click handler do not gain submit-handler origin under this extension. Existing
direct key-handler support remains separate. A native-click flag cannot authorize
a nested programmatic submission; scope barriers apply even while a genuine
keyboard, click or submit callback is active.

The normal target must cancel its own native form navigation. Verify cancellation
after product event dispatch, including the normal onsubmit return-false behavior;
a helper navigation guard cancelling a transition does not satisfy this condition.
Changing a submit button's enabled state after a verified submission need not
invalidate the historical event, but the existing input-focus receipt remains
strict through collection. Retain rejection
of document/same-document navigation, redirects, popups, frames and downloads
during the operation and its protected idle gap. Do not intercept and replay a
native form request as fetch/XHR. Existing same-tab scoped-click navigation keeps
its separate contract. Native validation that prevents submission is observed;
when a request was declared but none occurred, the existing missing-evidence
error applies. This does not establish a new validation-message assertion.
If browser validation or product cancellation prevents submit, the real key
receipt may remain valid with zero associated requests. Do not invent a submit
event or reject a UI-only validation Scenario merely because no submit occurred.
Every admitted submit that did occur must satisfy the product-cancellation rule.

Requests and responses still use the existing collector, origin/credential
policy, mock/live separation, matching rules and owned recordings. Actual wrong
query/body/response/UI evidence is FAILED under existing checks; missing or
ambiguous associated evidence, changed focus/identity and unsupported transitions
are ERROR with existing subsequent BLOCKED handling. A false outcome must never
be replaced by a direct API call. No new report status or core receipt is planned.

Frontend mocks remain explicit and cannot fall through to live services. Live
e2e must use actual browser traffic. Backend and contract can check their own
recordings but do not prove a browser form was submitted. Preserve safe default
representations and diagnostics: no typed value, selector, credential, URL or
response payload in generic errors.

## Scope and trust

This changes the optional browser helper and its tests/examples/documentation.
Core declarations, ports, runners and assertion vocabulary should remain byte
identical. If reliable evidence requires a core/YAML semantic change, stop and
explain the additional decision before implementing it.

The guarantee addresses cooperative mapping mistakes and accidental evidence
mix-ups. It is not a hostile-page sandbox, independent event attestation,
universal browser compatibility, adoption measurement or rollback guarantee.
The page-world instrumentation and native browser observations share trust
boundaries; multiple observations are not independent proof of product intent.

No other key, shortcut, general keyboard sequence, native form-navigation write,
file upload, authentication workflow, object absence, Flow, new assertion or
deeper inclusion is part of this task. Ordinary click/fill/open and scoped object
navigation must retain their existing behavior.

## Acceptance matrix

1. Gate: retain reproducible scratch commands/results for a positive/negative
   Chromium matrix and document the exact supported chain and limitations.
2. Positive helper cases: one valid native form submission, observed key receipt,
   listener/property/delegated handlers, fetch/XHR, supported Promise/native-await
   continuations, and independent explicit mock/live evidence.
3. Negative association: requestSubmit/submit/click/dispatch, other forms,
   same-path background requests, nested synthetic handlers, timers, stale or
   duplicated submissions, removed/replaced input/form/submitter, focus loss and
   source changes cannot produce a false pass.
4. Product semantics: preventDefault, stopPropagation, handler return values,
   validation and already-prevented keys are not repaired. Missing requests,
   multiple requests and actual wrong queries retain existing classifications.
5. Navigation/transport: native document submits, unsupported transitions,
   credentials/origin rules, native async limits, explicit mock consumption and
   cleanup remain enforced.
6. Consumer: freeze a new neutral normal target before adapter code. Run the same
   approved search Scenario on two handler forms, honestly described as variants
   when sharing an application. Check one actual search, expected response and
   rendering, one key pair, one user/context, zero API-port sends and cleanup.
   Preserve ignored submit, wrong-query, stale-render and programmatic-submit
   controls. Original target sources and Scenario remain unchanged.
7. Independent mechanism and consumer audits, relevant focused regressions,
   final sequential full suite, both supported dev-only Python environments,
   litmus, documentation sentinels, lock, hygiene and diff checks must pass.
8. Freeze equality of core, existing declarations, dependencies, CI workflow
   and prior sample targets; review all public changes for neutral sources.

## Delivery

Record actual commands, exit codes, supported/unsupported cases, independent
findings and corrections, accepted files and a short maintainer summary. Local
acceptance is distinct from hosted CI and publication. Submit only the accepted
public files, through a dedicated branch and PR. No workroom access or changes.
