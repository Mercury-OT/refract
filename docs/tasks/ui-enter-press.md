# Explicit Enter on an already focused search input

Status: maintainer approved the expression and failure rules on 2026-11-01,
starting main `c3e750d`. Real-browser association feasibility must pass before
implementation. Development, independent audit and architect acceptance precede
the authorized task-branch submission, green PR checks, merge, green main checks
and cleanup. No private workspace or existing product is accessed or changed.
Development, independent audits and architect acceptance subsequently passed;
see the [delivery record](ui-enter-press-acceptance.md) for actual checks and limits.

## Purpose and expression

Verify a keyboard-specific obligation: fill a search input, press Enter, and
check the actual query, response and rendered results. A successful direct API
request or a click on a search button does not prove this keyboard behavior.

Keep schema_version: 1, current metadata/parameters/steps/expect layout, one
action per leaf, one-level includes and the existing assertion vocabulary.
Add only `do: press`, one literal logical `target`, and literal `key: Enter`.
Key is required for press and forbidden on other actions. Null, other keys,
dynamic references, modifiers, sequences, repeats, value, duration, object_id
and polling are rejected on press. Existing expectations and stopping rules are
unchanged. This adds a bounded primitive, not computation, so it does not revise
R1. Existing declarations do not need migration.

The approved consumer has open, fill and press leaves. A new neutral sample
application has fixed public sample records, searches name substrings in place,
and owns its ordinary HTML/JavaScript behavior. The adapter does not prepare data,
change the page, inject identity, or repair search. Freeze normal target sources
before writing mappings; faulty variants are separate controls. Response checks
require status 200, a one-member list and the expected name. UI checks require
one expected-name row and zero known nonmatching-name rows; this is not a claim
that all possible unexpected UI rows or pagination have been checked.

## Feasibility and browser boundary

First demonstrate actual trusted Enter delivery and action-origin association in
Chromium, including keydown/keyup and property/delegated handlers. Challenge
same-path background work, timer and synthetic nested events. Reuse existing
bounded Promise/native-await association only where actually demonstrated.
Matching a URL, query, response or time window is never causal evidence.
Record what is supported and what remains diagnostic. Stop if no bounded reliable
route exists; do not weaken the declared checks to obtain a green result.

Gate result on 2026-11-01: passed before core/browser implementation. Thirty-six
exploratory cases compared baseline and candidate instrumentation; a final
twelve-case real-Chromium/native-collector matrix confirmed keydown/keyup native
await, same-path timer/shared-background isolation, synthetic inline key/change/
click isolation, and rejection of focus theft/restoration and native activation.
Exploration found that adding key handlers alone was insufficient: parsed nested
synthetic callbacks could inherit origin, and focus callbacks could run inside
the trusted handler. The implementation therefore requires a null invocation
boundary for synthetic dispatch and sticky focus invalidation. These findings
are retained as regression controls, not broad-browser or product-adoption proof.

The first helper supports a unique visible, enabled, editable ordinary HTML
text/search input in the main document. Require that exact element already has
focus. Focus checks are observations; do not click, call focus, search another
page, force an interaction or use locator.press's implicit focus behavior.
Pin and revalidate selection/focus at actual trusted key dispatch. Send one
Enter down/up pair through the browser keyboard. No missing match, ambiguity or
wrong focus is repaired. A preflight rejection sends no key. A race after an
event has occurred fails visibly but cannot undo its product side effects.
Focus displacement during the active press invalidates that action even if the
page restores focus later. Keep this guard through collection. Nested synthetic
key callbacks establish an unassociated scope; inline/property handlers cannot
borrow the surrounding trusted handler's origin, including after native await.

Retain observed key delivery before evaluating assertions, including for a press
without a request expectation. Unsupported native activation, form submission,
document navigation, tabs, downloads and frames cannot become supported Enter
evidence. Do not broaden the separately delivered scoped-click navigation rule.
Reject unsupported transitions during press and its following idle gap. Check
the collected error ledger before the next authorized action resumes its own
existing navigation rules. This does not promise control over unbounded future
timers or newly prohibit a later explicitly declared ordinary click/open.
No generic focused/hidden/selected assertion, other key, shortcut, key repetition,
keyboard sequence, IME, contenteditable or textarea support is introduced.

## Core and adapter contract

Add an optional keyword-only Step.key and UiActionPermit.key, None by default.
Permit integrity includes key. Include expansion, prepared steps and review
output preserve the literal key. Operation interfaces continue to receive only
action inputs and execution identity, never expectations.

StepwiseUiDriver.supports_key_press(mode, key) is nonabstract and defaults to
false. A Scenario containing press requires exact True for the selected UI mode
before creating a UI context. Unsupported, malformed or failing capability
responses are errors; no fallback to another operation. Existing ordinary
drivers remain usable for their unchanged actions.

UiKeyPress is a frozen receipt containing key, target_matches, focused,
keydown_count and keyup_count. Completed press evidence must contain an owned
receipt: key is Enter, the three counts are strict integer 1, focused is exactly
True. Other actions must not return it. Evidence identity still binds run,
action, step, user, session and context; this is a checked adapter claim, not
independent attestation. Retain an owned receipt in the step report and exclude
receipt payloads from default repr. Reused, malformed or mismatched evidence
cannot pass. Action-only and receipt ownership tests are mechanical gates.

Backend can execute a declared request but does not perform or prove Enter.
Contract consumes backend recordings and does not prove keyboard behavior.
Frontend requires explicit mocks; live e2e uses real browser traffic. No repair
request, mock-from-expectation construction or missing-mock live fallback.

## Failures and evidence

Missing/nonunique/unusable target, wrong focus, invalid key delivery, missing or
ambiguous associated request, or unavailable capability produces existing ERROR.
Later leaves become BLOCKED under the existing error policy. A uniquely
associated request with incorrect query or an observed wrong response/UI value
produces ordinary FAILED. Ordinary failure continues unless on_failure: stop.
No new report status is introduced. An ERROR is not proof of a product defect.
Background requests remain diagnostic and may not fill missing action evidence.

Protect against cooperative mapping errors, accidental focus changes, stale or
background evidence and mutation of shared objects. Do not claim resistance to
hostile page/adapter code in the same process, complete coverage, independent
evidence from multiple browser APIs, or quantified adoption savings. Errors and
default representations must not reveal typed input, selectors, URLs, credentials
or response payloads. Preserve existing deadline, mock, origin, session and
cleanup boundaries.

## Acceptance matrix

- Loader: positive literal Enter, all wrong shapes/keys/actions, valid/invalid
  include substitution, expansion and one-level nesting limits.
- Core: legacy opt-out before context, strict capability and receipt types,
  signed key, owned arguments/receipts, no expectation leakage, no-request press,
  replay/user/session mismatch, live/mock, failure/blocked rules.
- Browser: one trusted pair, unique focused target, wrong focus/no target/
  duplicates/disabled/readonly/wrong element kind, dispatch-time replacement or
  ambiguity, no auto focus/click, no synthetic-event substitution.
- Association: listener/property/delegated handlers, existing supported async
  paths, same-URL background, nested synthetic work, timer, multiple matching
  requests, wrong query, keydown and keyup effects, no API repair.
- Unsupported navigation/activation, stale document, cleanup and next action
  isolation; normal click/fill/object selection/navigation regressions remain.
- A frozen neutral consumer runs the same approved search Scenario through live
  Chromium; explicit faults for ignored Enter, wrong query, stale/wrong results
  and focus theft do not pass. Separate mock results are not live evidence.
- Independent core/browser audit, actual full browser suite, dev-only core,
  litmus, documentation examples, lock, hygiene and diff checks pass. No new
  dependency, assertion term, product-specific source or private information.

Delivery records actual commands/results, supported boundaries, independent
findings and fixes, accepted files and information-source review. Object absence
and Flow remain paused/outside this task.
