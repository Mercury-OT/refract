# Exact-ID object absence

## Authority and scope

The maintainer approved the complete create / verify existence / delete example
and the rules below on 2026-11-09, starting from main `c9410f5`. Implementation,
independent audit and architect acceptance are authorized; submission, PR checks,
merge, main checks and cleanup are authorized only after successful acceptance.
Public code and neutral synthetic consumers are the only information sources.
No private workspace or product access or modification is in scope.

Preserve `schema_version: 1`, existing do/expect structure, one-level inclusion,
Flow, user/session mappings and failure continuation. Add one assertion, not a
query language, retry engine, new action, new port or new report status. No R1
transformation, branching, looping or JSONPath exception is involved.

## Approved declaration

`expect.backend_state` gains `check: object_absent`, requiring exactly `object`
and `id`. `object` is a nonempty literal business name, not a storage table.
`id` follows the existing object-state reference rules: parameter, earlier
response or named result, resolving to an exact integer or nonempty string.
No literal ID, bool, null, empty string, container, self/future reference or
direct concat is added. Known invalid references fail loading; unavailable or
invalid runtime IDs block the consuming action. No field or value is accepted.

The approved Scenario creates a record with a run-unique code, checks 201,
success and a returned ID, reads that ID and checks 200, response identity and
independently observed committed code, then deletes that ID, checks 204 and
object absence. The first two steps explicitly stop on assertion failure.
Publish the English equivalent as a runnable synthetic SQLite example.

## Observation and truth boundary

Reuse `ObjectStateProbe.observe_object` and the existing exact query identity,
source, completeness, snapshot ownership and sensitive-data requirements.
Group assertions by business object and exact ID type/value. Equality and
absence for the same object share one snapshot and the union of fields needed
by equality checks; absence alone sends `fields=()`. An empty field selection
still requires a real lookup. The probe receives no expected values or checks.

| Observation | Result |
| --- | --- |
| Valid complete lookup with zero matching objects | Absence check passes. |
| Valid complete lookup with exactly one matching object | Absence check FAILED. |
| Multiple objects, invalid/wrong/stale identity, incomplete facts or query exception | ERROR. |
| Missing object probe | Visible degradation; strict passage is impossible. |
| Missing/invalid selector dependency | BLOCKED before the consuming action. |

Keep equality's existing zero-match FAILED behavior. Retain actual observations
as core-owned copies, with safe errors/default representations. A valid empty
result is distinct from a missing result. No default, coercion or fabricated
object is allowed. Mixed contradictory assertions are evaluated honestly; do
not skip either or query until one passes.

Absence describes the reviewed source and exact selector, not every cache,
replica or backup. A permission-filtered or paginated empty view cannot prove
storage absence. Query identity and `complete=True` do not authenticate an
adapter's claim; mapping review, positive existence controls and faulty-target
tests remain necessary. A soft-deleted surviving record is present: check its
deletion flag with existing equality instead. Denied creation without a known
ID needs a separately approved selector/evidence design and is not covered.

## Execution and projections

Observe once after the real response, including an ordinary failed response
assertion. Explicit API polling keeps existing rules: one observation after a
successful terminal response, none after timeout/FAIL/SKIP. No new asynchronous
waiting, eventual-consistency promise or requestless observation is added.

Backend and live e2e share the evaluator, including request-associated UI
steps. Frontend mocks never query storage; contract reports state assertions
outside its scope and does not convert storage into compatibility evidence.
Preserve include expansion, named-result IDs, Flow references, users/sessions,
continuation and strict report aggregation. Storage facts are not new values
available for subsequent references or named results.

## Verification matrix

- Loader: valid reference forms; absent/extra keys; invalid names and IDs;
  wrong assertion section; self/future/unavailable sources; no direct concat.
- Runtime: complete zero/one/multiple observations; no result; incomplete facts;
  stale/wrong query identities; failed queries; missing probe; strict ID types;
  mixed equality/absence sharing one lookup; copied evidence; sensitive output.
- Projections: backend/live e2e parity, request-associated UI coverage, no
  frontend/contract storage call, no accidental StateProbe use for absence,
  existing response failures and polling semantics, blocked dependencies.
- Composition: one-level include with supplied/named-result ID and a sequential
  Flow consumer preserve selection identity and failure behavior.
- Real SQLite: committed deletion passes; successful response without deletion
  fails; uncommitted deletion fails through the separate read-only connection;
  wrong-target deletion fails; positive existence control catches an always-empty
  probe; incomplete or failed acquisition cannot pass. No changes to products.
- Independent synthetic domain: exercise equivalent absence semantics with a
  neutral documents consumer without asserting production adoption value.
- Existing guarded full suite, offline core checks, litmus, documentation
  sentinels, lock check, hygiene and diff checks pass. Public text stays English.

Record commands, actual results, independent findings and their resolutions in
the acceptance record. A green synthetic demonstration proves only the stated
mechanism and controls, not arbitrary adapter fidelity or real adoption cost.
