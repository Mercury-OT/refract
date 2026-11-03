# Explicit Escape on an already focused search input

Status: the maintainer approved the expression, failure rules, implementation,
independent audit, acceptance and subsequent task-branch submission on 2026-11-03.
Starting main: `1ae784d`. Real-browser feasibility must pass before implementation.
Publication follows acceptance, green PR CI, merge, green main CI and cleanup.
Development, independent audits (including the rejection-stall repair) and final
architect acceptance have passed; see the [verification record](ui-escape-press-acceptance.md).

## Purpose and approved expression

Verify a real keyboard cancellation: open search, fill the declared text, observe
an expanded suggestions panel, then press Escape to close it without changing the
text. Clicking outside, hiding a panel by script or repairing focus cannot stand
in for the declared action. This is a bounded operation, not a value transform;
it does not revise R1 or add an assertion term.

Keep schema_version 1, the existing structure and one-level inclusion. Add only
literal `Escape` to `do: press`, alongside the unchanged Enter contract. No new
declaration field, modifier, repetition, sequence, dynamic key, object_id, value,
duration or polling is accepted for press. Escape accepts only expect.ui, even
when a forbidden expectation section would be empty. At least one assertion per
Scenario remains required; a particular Escape step may have none.

The approved consumer is records.dismiss_search_suggestions, description of
closing suggestions while preserving typed content, users [reader], and parameter
search_text=report. Its three leaves are:

1. open_search: open records.search_page, on_failure stop, UI visible on
   records.search_input.
2. enter_search_text: fill records.search_input from search_text, on_failure stop;
   UI objects_matching_count for value=search_text and suggestions_visible=true,
   each count 1 on records.search_input.
3. dismiss_suggestions: press records.search_input with key Escape; the same UI
   checks require suggestions_visible=false and value=search_text, each count 1.

suggestions_visible is an observed semantic field, not a new assertion. A read-only
mapping derives it from the actual associated panel. Missing/ambiguous structure
or unreadable association is unavailable evidence, never false or an invented
empty collection. Freeze neutral application sources before adapter integration;
do not change an existing product or use private source material.

## Feasibility and supported browser boundary

First demonstrate in actual Chromium: one trusted Escape down/up pair, dismissal
with input preserved, no keypress prerequisite, rejection of wrong focus, and
synthetic events not substituting for real delivery. Retain commands and results.
Only a unique visible enabled editable text/search input in the main document is
supported. It must already have focus and remain the same mounted, focused object
through evidence collection. A transient focus loss remains an error even if
focus is restored. No implicit focus, click, scroll or replacement target.

Escape is separate from Enter's keypress/default-submitter/form association.
Preserve all Enter behavior and tests. Observe real keydown and keyup exactly
once, without modifiers, repeat or IME. Preserve document/navigation, tab, frame,
download and protected idle-gap guards. A later authorized action resumes its
own documented rules. This slice does not support dialogs that remove the input
or move focus, arbitrary keyboard shortcuts, native navigation or new transports.

Escape traffic remains diagnostic, including immediate, deferred and synthetic
callbacks; it cannot satisfy Escape or a later click/Enter. A mock may neither
consume a later action's fixture for Escape background work nor fall through to
live API services. Reuse the existing conservative post-hover mock policy for
this UI-only action if needed; document its exact context lifetime. Do not infer
causation from URL matching or timing. Existing origin, credentials, request
evidence and deadline rules remain unchanged.

The persistent mock quarantine belongs to BrowserSupport. Custom drivers retain
the existing rules for explicit diagnostic mock fixtures; diagnostics cannot be
associated Escape traffic, provider evidence or a substitute for a later action's
own request. This task does not introduce a universal custom-driver scheduler.

## Core, projections and failures

Reuse supports_key_press(mode, key), default false, and the existing UiKeyPress
receipt. Check capability for every distinct requested key in the selected mode
before authentication/context creation; support for Enter alone does not imply
Escape. Keep action-only inputs, signed permits, owned snapshots, receipt privacy
and execution/user/session/context identities. Receipt key must equal the permit,
counts must be strict integer 1, focused must be exactly true. Other actions
cannot claim key delivery. Escape cannot return a skip or associated traffic in
place of a completed receipt. Programmatic Scenario objects must obey the same
action limits before UI effects, without weakening loader rejection.

Frontend and e2e execute the real action and evaluate page evidence. Backend
reports a requestless Escape step NOT_APPLICABLE with unchecked UI obligations;
a purely UI Scenario is EMPTY, never PASSED. Contract cannot prove Escape. Keep
the existing combined-report rule: EMPTY backend plus PASSED e2e is DEGRADED.
No new status, automatic projection selection or changes to Flow/include failure
semantics. Include expansion and Flow scheduling preserve the literal key.

Unavailable/ambiguous target, wrong focus, incomplete/invalid delivery or missing
observation produces ERROR and existing subsequent BLOCKED behavior. Actual
delivery with a panel still visible or text changed produces ordinary FAILED;
default continuation and explicit on_failure stop remain. A late error cannot
undo product effects that already occurred. ERROR is not proof of a product bug.

These mechanisms address cooperative implementation mistakes, stale evidence,
accidental identity/focus changes and background contamination. They are not
attestation against hostile same-process adapter/page code. No claim of independent
evidence from multiple APIs, universal browser support or measured adoption gain.
No selectors, typed text, URLs or raw exception payloads in default repr/errors.

## Acceptance matrix and delivery

- Loader: literal Escape, unknown/dynamic keys, wrong action fields, all forbidden
  expectations including empty, zero-step checks within an asserted Scenario,
  one-level include expansion, named results and Flow boundaries unchanged.
- Core: opt-out and exact capability typing before effects, mixed Enter/Escape,
  strict/mismatched/missing/extra receipts, replay and identity rejection, owned
  arguments/results, no expectation leakage, skip/traffic refusal, live/mock,
  error/failure/stop/continue and projection aggregation.
- Browser: trusted pair and normal dismissal; missing/duplicate/disabled/readonly/
  replaced/hidden target, wrong or stolen/restored focus, synthetic substitution,
  unsupported transitions, background contamination, mock isolation and cleanup.
- Consumer: two ordinary event-handler implementations with unchanged frozen
  sources and identical Scenario/mapping; normal frontend and live e2e pass.
  Ignored Escape, clearing text, suggestions never opened, missing/ambiguous panel,
  wrong focus and duplicate input cannot pass. Retain actual step status/evidence.
- Independently review core and browser/consumer changes. Run focused checks,
  guarded full regression with real Chromium, dev-only supported Python versions,
  litmus, documentation examples, lock, hygiene and diff checks. Assertion vocabulary
  stays byte-identical. Record actual results, findings/fixes and accepted files.

Deliver code, tests, a runnable neutral consumer, documentation and acceptance
record. Object absence remains paused. Do not access or modify the private
workroom, change products, expand Flow or introduce a graphical workbench.
