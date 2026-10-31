# Selecting a UI control for an observed business object

Status: maintainer approved the object_id YAML and failure rules on 2026-10-31,
against main `19d5ef1`. Development, independent audit and architect acceptance
are required. The maintainer also explicitly authorized submission, PR checks,
merge, main CI verification and branch cleanup after acceptance. This is not
permission to merge failing checks. Sources are public implementation and newly
authored neutral fixtures; no private product or workspace is an input.

## Purpose and scope

A fixed logical target identifies a class of control; an optional object_id
selects which business object's control to click. This makes the selection
reviewable without hiding previous-response lookup in an adapter. It does not
prove reduced adoption/review cost or certify arbitrary adapter mappings.

Keep schema_version: 1, current do/target/expect structure and one-level includes.
This first slice adds object_id only to click leaves. Ordinary open/fill/click
steps retain their existing semantics. No new action, assertion, selector DSL,
query/filter expression, dynamic logical target, nested locator, implicit search,
pagination, API fallback, Flow, new report state or object_absent is authorized.
No expression/branch/loop/JSONPath or value transformation is introduced; R1 is
unchanged. Reference binding supplies existing data, not executable syntax.

## Declaration and execution contract

```yaml
- id: open_editor
  do: click
  target: records.edit_button
  object_id: {from_step: create, response_field: id}
  expect:
    ui:
      - {check: visible, anchor: records.editor}
```

- target remains a nonempty literal logical control name. object_id is a nonempty
  string or exact integer, or an existing parameter/prior-response/member/named-
  result reference resolving to one. Reject bool, null, float, empty string,
  containers and direct concat. Referencing an already composed string parameter
  retains the existing parameter contract. No implicit ID coercion is allowed.
- The field is optional, but explicit null is not omission. It is forbidden on
  open, fill, wait, request and include nodes. It is selection input, not an
  assertion and does not make an otherwise assertion-free Scenario valid.
- Validate known values while loading and after include parameter substitution.
  Resolve the entire step before a permit or action. Missing/null/invalid runtime
  response values produce local BLOCKED under existing dependency rules; independent
  later steps retain their current continuation behavior. Invalid declarations
  fail loading before target actions.
- Include mapping, named-result use, expansion and impact inspection preserve
  this field and its sources. Parent callers cannot replace child actions or
  expectations. No deeper composition or result shape is added.
- An unsupported UI adapter fails before any context or business action in that
  selected projection. Backend may execute a UI step's declared request as today,
  but cannot claim to have checked UI selection; contract also does not check it.
  Neither projection may infer selection from a matching response alone.

## Operation and evidence boundary

Add optional sensitive object_id to Step and UiActionPermit. It is part of the
permit signature and strict integrity comparison. No expectation, request
constraint, unrelated binding or full declaration reaches an operation port.
Keep existing user/session/context/replay checks and ownership protections.

Add a default-false `StepwiseUiDriver.supports_object_targeting(mode)` capability.
Only exact True opts in for that mode. Existing drivers keep working for ordinary
clicks, and fail visibly for scoped clicks instead of silently ignoring the ID.
The perform_step signature remains unchanged.

A scoped click must return a bounded `UiObjectSelection` receipt containing the
actually selected object_id plus exact integer `object_matches` and
`control_matches`, both 1. Add optional `UiActionEvidence.object_selection` and
retain an owned sensitive copy on StepResult after validation. Scoped selection
requires this receipt even for a click with no request. Missing/wrong-type,
wrong-ID, bool/int confused or nonunique receipts are ERROR. An unscoped action
must not return a selection receipt. Default repr must not expose IDs or receipt
payloads. The receipt provides local consistency, not independent attestation.

## Browser support contract

Extend BrowserSupport.perform with an optional ObjectTarget mapping, mutually
exclusive with url/selector:

```python
ObjectTarget(rows=".record", control="button.edit", read_id="row => ...")
browser.perform(context, permit, object_target=mapping)
```

ObjectTarget is a frozen product-owned mapping with native CSS row and relative
control selectors and a read-only JavaScript identity reader receiving one actual
row, never the requested ID or assertions. This is adapter code, not Scenario
syntax, a new mapping language or a sandbox. The reader may inspect an existing
attribute, ordinary detail link or form action; no test-only identity attribute
is inserted into target DOM. Mapping exceptions and invalid/missing identities
are errors, not silently discarded nonmatches. Unavailable identity is not
inferred from labels, order, expected values, response order or database contents.

The helper owns the selection and interaction:

1. Read the current visible row scope, actual identities and controls. Compare
   IDs strictly. Keep ID transport lossless: JavaScript unsafe numeric identities
   are rejected before clicking; never round a Python integer into another ID.
   Ordinary string IDs remain exact strings. If the helper cannot represent an
   ID faithfully it must fail visibly, not coerce it.
2. Zero matches may use the existing bounded action-readiness deadline, with no
   extra navigation, searching, pagination, requests or retries of the action.
   An unresolved identity cannot be treated as a complete zero match.
3. More than one matching object, or more than one visible control in its row,
   is an error immediately. One row with a not-yet-ready control may wait within
   the same deadline. Never use first/last/index to resolve ambiguity.
4. Pin the selected row/control, and recheck its identity and uniqueness at the
   trusted click boundary before application click handlers run. DOM replacement,
   ID changes, duplicate insertion or an event on another element must not redirect
   the click to a different object. Prevent rejected click dispatch and report
   ERROR. No synthetic click, force click or altered product DOM is a substitute.
   This does not undo earlier pointer/hover side effects or promise a transaction
   across arbitrary hostile browser code. Actual browser tests exercise races.
5. Run exactly one permitted click, then retain existing bounded completion,
   actual request association, native-await, mock/live, credential and cleanup
   rules. Construct the receipt from actual selected facts, not a permit echo.
   Request expectations still check the actual object ID in observed traffic;
   no correct API request is sent to repair a wrong browser request.

The initial helper uses the existing current-document action-completion boundary.
A scoped click that navigates/replaces the whole document cannot provide its
retained receipt and must fail visibly. The approved consumer opens an in-page
editor; full-document receipt transport is not part of this slice and has a
negative browser control rather than an untested support claim.

No match by deadline, ambiguity, missing mapping/evidence or browser failure is
ERROR and stops later leaves under current rules. Snapshot/readback of unrelated
UI objects is unchanged. No storage state or absence assertion is introduced.

## Consumers and unchanged product boundary

No existing real or public target application will be modified to make selection
work. Existing public examples lack row-edit controls; therefore add two NEW,
neutral synthetic UI implementations for mechanism validation, not adoption
claims. Use ordinary existing-in-that-fixture detail-link and edit-form-action
identities, different DOM/control structures, and independently implemented UI
rendering. Freeze their sources before writing target mappings and integration
checks. Do not patch their DOM or add identity metadata from an adapter/test.
Fault-injected clones are separate negative controls, not changes to the normal
consumer. Shared synthetic backend transport is permitted and must be disclosed.

The approved six-step example is API create -> open list -> click this object's
edit -> fill -> save -> API read. The synthetic contract performs a real GET on
edit and PATCH on save. This is a live e2e consumer; it does not verify a creation
form, every product's editor behavior, or physical storage persistence. Seed
visible decoys so the target is not first. No private product data is used.

## Acceptance matrix

- Declaration: valid literals/parameters/response selectors/named results; invalid
  types/extra fields/unsupported actions, explicit null, direct concat, forward
  references, assertion-free scopes; known-invalid include substitutions.
- Binding/reuse: zero/negative integer and string identity retain exact types;
  missing/null/wrong runtime values block before permit/action; independent later
  work and ordinary failure policy remain; child-local rewrites, repeated include
  invocations, parameter mapping, expanded review and result-consumer impact.
- Port boundary: old adapters reject scoped flows before context/business actions;
  exact capability types; no expectations leak; permit ID mutation and mismatched
  receipts fail; empty/no-request scoped clicks cannot silently pass; repr safety.
- Real browser, live and mock as applicable: target not first, reordered rows,
  ordinary detail-link/form-action identity, delayed presence, absent target,
  duplicate rows, duplicate controls, missing/invalid identity, bool/int and
  string/int distinctions, unsafe number transport, sensitive ID omission, no
  DOM identity injection, no secret selector interpolation, no extra actions.
- Race and evidence: replacement or identity/ambiguity changes before click,
  nested click targets, stale/replayed/user/session permits, wrong actual GET or
  PATCH ID, unchanged background/async/native/mock isolation and cleanup.
- Consumers: both neutral UI implementations use the same business Scenario and
  real HTTP API create/read. Record actual clicked/updated objects and preserve
  controls for wrong-row behavior. Report adapter mapping scope honestly.
- Regression: focused core/browser tests, declaration/review/port litmus, full
  suite with real Chromium, dev-only core, lock, hygiene, diff checks; independent
  audit challenges selection races and identity/evidence handling. No benchmark
  or global adapter-certification claims.

## Delivery artifacts

Implementation and focused tests; public English Scenario example and mapping
instructions; SCENARIO.md, browser-support/onboarding and selected Python migration
notes where changed; roadmap status; separate acceptance record with actual
commands/results, source snapshots, audit findings and remaining limits.
Only after independent audit and architect acceptance may the already-authorized
submission workflow run. No private workspace is accessed or changed.
