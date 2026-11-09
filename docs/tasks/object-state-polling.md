# Bounded object-state observation

## Authority and scope

The maintainer approved this slice on 2026-11-09, starting from main
`672f0c8`: specification, development, independent audit and architect
acceptance, followed by submission and merge only after acceptance and green
hosted checks. Public code and neutral synthetic consumers are the information
sources. Private workspaces and products are outside scope.

Preserve format 1, do/expect, one-level inclusion, Flow, sessions and failure
continuation. Add an optional step policy `object_poll: {on_timeout: FAIL}`.
The request or UI action executes once; only read-only object observation is
repeated. This is an explicitly approved bounded observation policy, like the
existing bounded GET observation policy, not a general Scenario loop or value
transformation. No assertion, selector, report status or probe port is added.

## Declaration and selection

The policy requires exactly `on_timeout: FAIL`. Reject empty/unknown policy
fields, SKIP, inline budgets, and non-mapping policies. It requires a declared
request and at least one existing object-state assertion. All backend-state
assertions in this step must be `object_field_equals` or `object_absent` for one
business object and one exact typed ID. Multiple field conditions are allowed;
they must hold in the same fresh snapshot. Object absence plus field equality
is not made true by accumulating different snapshots.

Do not combine this policy with GET `poll` or span assertions: those policies
have their own budgets and retry semantics. No requestless observation, hover,
Escape, wait, include-level policy or nested polling is added. Request-associated
UI actions use the same live observation evaluator. Known-invalid selection
fails loading; IDs that become unavailable, invalid or inconsistent after
binding block the action before side effects. Existing references, strict ID
types and include/Flow mapping apply unchanged. Expansion exposes the policy.

## Execution and deadline

Reuse the caller's validated `PollConfig(timeout, interval)` and injected
monotonic `now`/`sleep`. The object budget starts immediately before the first
query, after the actual response and existing response evaluation. It does not
replace action, HTTP or host timeouts. Make an initial read, then retry only
complete, correctly attributed, unambiguous snapshots whose checks do not yet
all match. Each read gets a new observation identity and fresh source snapshot.

Read duration counts toward the budget. Sleep at most the remaining budget;
do not start a read at or after the deadline. A result returned at or after the
deadline cannot pass, even if its object conditions match. Retain the returned
evidence and report timeout as FAILED. Query errors or invalid, incomplete,
ambiguous or wrong-identity facts terminate immediately as ERROR, including a
late erroneous result. No retry hides acquisition failure. Missing probe retains
visible degradation; unavailable selectors remain BLOCKED before action.

Keep every valid snapshot, including intermediate mismatches, as an owned
sensitive report value. Final object checks describe the terminal snapshot;
intermediate mismatches are observations, not accumulated failing assertions.
Record value-free object-wait metadata: configured timeout and interval,
attempt count, elapsed time and terminal outcome. HTTP attempts and recorder
response identity remain unchanged. Eventual object success cannot erase a
failed response/request/UI check. Existing step and Flow stop/continue policies
still apply. No state facts become response references or named results.

## Reader feasibility and honest guarantees

The unchanged probe port is synchronous. The framework cannot interrupt an
arbitrary blocking adapter. A polling consumer must provide a reader with a
finite per-read timeout and reliably release read resources/transactions.
Deadline enforcement stops new reads and rejects late success; it is not hard
cancellation and does not promise the caller returns by that exact deadline.

Before implementation, a real SQLite exact-primary-key reader was exercised
under an exclusive lock: its configured one-second busy timeout raised an
error, all read connections closed, and subsequent separate connections saw
newly committed presence and deletion. SQLite's busy timeout bounds lock waits,
not arbitrary query execution. The finite indexed lookup is the demonstrated
consumer; no generic storage or cancellation guarantee is claimed. Preserve
reproducible tests of timeout, closure and fresh committed snapshots.

## Evidence and projection boundary

Backend and live e2e observe after the real request once. Frontend mocks never
query storage; contract never promotes storage into compatibility evidence.
Existing no-policy one-shot behavior and GET polling remain unchanged.

A match means the conditions held in one observed snapshot within the budget.
It does not prove continuous absence, lack of later resurrection, every replica,
or causality. Complete/source/identity claims are still adapter claims, not
authenticated truth. The probe receives only selection and execution identity,
never expected values, retry conditions or the Scenario. Keep existing safe
errors, default representations and explicit sensitive-report access.

## Verification and acceptance

- Declaration: positive API/request-associated UI, strict policy shape, wrong
  locations, missing request/assertion, multiple selectors, mixed policies,
  reference binding, expansion, one-level include and Flow propagation.
- Deterministic clocks: immediate match, delayed match, timeout, exact deadline,
  slow late match, clamped sleep, no read after deadline and no business replay.
- Evidence: all conditions in one snapshot; no cross-attempt accumulation;
  immediate query/shape/completeness/identity/ambiguity error; missing probe;
  retained copied snapshots and value-free wait metadata.
- Failure: failed HTTP/UI checks survive eventual match; timeout follows normal
  continue/stop policy; missing ID blocks before action; one-shot regression.
- Projections: backend/e2e parity, real request-associated UI evaluator path,
  frontend/contract no probe call; HTTP/recorder attempt identity unchanged.
- Neutral consumer: create, independently verify existence, DELETE once with
  202, independently observe a later committed deletion. Wrong/no deletion,
  uncommitted deletion and failed/incomplete reader cannot pass. A separate
  documents consumer checks the same policy without storage-specific core code.
- Guarded full suite, supported dev-only interpreters, litmus, documentation
  sentinels, lock, hygiene and diff checks pass. Independently audit the final
  frozen files and record actual commands, outcomes and resolved findings.

Not included: generic cancellation, background jobs in adapters, action retries,
new clocks or budgets in YAML, temporal logic, multiple-object waiting, new
assertions, cleanup guarantees, private integrations or adoption-value claims.
