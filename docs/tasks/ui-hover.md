# Explicit UI hover with page-only evidence

Status: the maintainer approved the proposed expression, projection treatment
and bounded implementation on 2026-11-02. Starting main: `272dad7`.
Real-browser feasibility precedes implementation; independent audit and architect
acceptance precede the explicitly authorized task-branch submission, green PR
checks, merge, green main checks and branch cleanup.

## Purpose and approved expression

Expose a previously implicit UI action: move the pointer onto a logical control,
observe the revealed menu, then click an item as a separate step. An adapter must
not hide hover inside a click or change the application to manufacture a result.
This adds only `do: hover` and the existing literal `target`; schema_version 1,
metadata, parameters, steps, expectations and one-level inclusion remain.
It is an operation primitive, not a value transformation or a revision of R1.

The approved consumer has three steps: open a records page and check zero visible
`Archived records` menu items; hover the menu trigger and check one matching item;
click that item and check the actual GET `[records]` with `status: archived`, HTTP
200, success, a one-member response collection with the intended archived record,
one displayed archived record and zero displayed known active records. Open and
hover use `on_failure: stop`. Named participant `reader` is the sole user.
Parameters are menu_text=`Archived records`, archived_name=`Archived record`,
active_name=`Active record`. Preserve these approved business obligations.
The host prepares the fixed archived/active dataset; no adapter business seeding.

Hover may have zero or several existing `expect.ui` assertions. The complete
Scenario still requires at least one assertion. Reject hover value, key,
duration, object_id, poll and all non-ui expectation sections, including empty
request/response/backend_state sections. Do not silently ignore unsupported
checks. No optional coordinates, pointer path, repeat, timing field, object
selector, nested action, key or new assertion term is added.

## Projection and report behavior

Frontend and live e2e perform actual hover and evaluate UI checks. Frontend mocks
remain explicit and never fall through to live API services. Hover-related HTTP
is background diagnostic evidence only, never the provider for hover or a later
click. Later click request association retains its existing strict contract.

Backend does not open a page or hover. A valid requestless hover is a
NOT_APPLICABLE step with UI obligations in not_checked. It does not trigger
on_failure: stop. Later declared requests may execute directly and their backend
checks may pass, without claiming the UI was verified. A hover-only Scenario
selected for backend is EMPTY, not PASSED. Contract likewise cannot prove hover.
Existing aggregation remains: EMPTY backend plus PASSED e2e is DEGRADED; only
selected executed checks can establish a strict PASSED result. No new status or
automatic projection selection is introduced.

## Feasibility and browser evidence

Before implementation, exercise actual Chromium against neutral CSS and
JavaScript menus. Establish a reliable route to a unique, visible, unobscured
main-document target and observe the pointer at that exact DOM object, including
descendant hits. Pin the actual element and recheck uniqueness, connection and
hit target through collection; do not silently choose a replacement or first
match. Missing, duplicated, hidden, covered or replaced targets cannot pass.
Synthetic events cannot substitute for actual pointer delivery.

Use one pointer movement to the target. No hidden click, focus call, style change,
forced interaction, move-away-and-back sequence, API replacement or business
workflow is allowed. Already-positioned pointers and target movement must be
tested; absence of a new enter event is not proof that a new one occurred.
Bound the supported geometry to the proven route, and document unsupported
geometry rather than add general pointer choreography.
The verified route is an in-viewport center point with a trusted mousemove
receipt and a matching hit test. This slice does not scroll the target into view.

No hover callback receives a request-evidence origin. Test immediate and delayed
same-URL hover/background requests around a following authorized click; they must
never rescue a missing click request. Preserve network origin/credential policy,
mock isolation, replay protection, existing deadlines and exactly-owned cleanup.
After a context accepts its first hover, unassociated mock API traffic is
aborted with a diagnostic note. It may neither consume the ordered action
fixtures nor fall through to live services. This conservative context-wide
restriction remains for delayed work after hover; it does not infer which
background callback caused the request. Contexts without hover retain their
existing mock behavior, and live background handling is unchanged.
Reject unsupported navigation, document replacement, new tabs, frames and
downloads during hover and its protected idle gap. Preserve the next explicitly
authorized action's existing semantics after checking that gap.

Observation maps only actual visible DOM. The fixed menu region must be readable
before a zero count is reported; unavailable structure is ERROR, not an invented
empty list. A completed hover whose menu fails the declared check is FAILED.
Unavailable/ambiguous action or observation evidence is ERROR, with subsequent
BLOCKED handling. Ordinary assertion failures retain the existing continuation
policy. Failures cannot undo effects already produced by the application.

## Bounded port addition

Add nonabstract `StepwiseUiDriver.supports_hover(mode)` defaulting to False.
Require exact True for the selected mode before UI context creation. Existing
drivers keep their current behavior until they explicitly support this action.

Add frozen keyword-only `UiHover(target_matches, pointer_on_target)` and optional
`hover` fields on UiActionEvidence and StepResult. Core requires an exact UiHover,
target_matches as strict integer 1 and pointer_on_target exactly True. Other
actions must not claim this receipt. A hover cannot return a tolerated skip in
place of delivery evidence, nor claim associated traffic. Retain owned copies
and hide receipt payloads from default repr. Existing run/action/step/user/
session/context identity and permit protection apply unchanged.

Action interfaces still receive operation inputs only, never assertions. This
receipt is a checked adapter claim addressing accidental mapping/evidence errors;
it is not independent attestation or protection against hostile same-process
adapter/page code. No approval or security platform is added.

## Verification and delivery

1. Record pre-implementation Chromium feasibility cases and limitations.
2. Loader and expansion: allowed hover, forbidden fields/expectations, includes,
   Flow scheduling and unchanged schema version/one-level restriction.
3. Core: default capability refusal before context, strict capability/receipt
   types, skip rejection, extra traffic, replay/identity mismatch, owned copies,
   no expectation leakage and safe diagnostics. Keep only one UI step loop.
4. Projections: mixed backend NOT_APPLICABLE/PASSED, hover-only EMPTY, combined
   EMPTY/PASSED aggregate, contract not-checked, frontend mock and live e2e.
5. Browser: real CSS/JS hover, known empty/visible menu, target ambiguity,
   obstruction, replacement, stale/synthetic receipts, already-positioned pointer,
   idle-gap transitions, background contamination and complete cleanup.
6. Consumer: freeze neutral target source before adapter integration; unchanged
   positive variants, ignored hover, permanently visible menu, wrong response/UI
   and missing menu-region controls. API success cannot replace hover evidence.
7. Independent core/browser audit and final acceptance; focused, full guarded,
   dev-only supported Python versions, litmus, lock, hygiene and diff checks.
   vocabulary.py stays byte-identical. Record actual counts, failures and repairs.

Deliver code, tests, one complete approved Scenario, a public executable consumer,
current SCENARIO/browser support/migration documentation, roadmap and acceptance
record. Record prior browser Flow delivery through PR #48/main `272dad7` while
preserving its historical local acceptance record. Public sources and English
neutral examples only; do not access private workspaces or products.
Object absence, Flow branching/editor, files, additional keys, hover object_id,
hover-request correlation and new assertions remain outside this task.
