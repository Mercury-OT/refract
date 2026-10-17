# Continue after assertion failures

## Authority, sources, and delivery boundary

The maintainer approved default continuation after ordinary assertion failure,
optional leaf-step `on_failure: stop`, and retaining `schema_version: 1` on
2026-10-17. Specification, development, independent audit, and local acceptance
are authorized. Submission is not: no staging, commit, push, PR, or merge.
The starting public main is `d2a5ed9e8886ca54eff76b567c157875df6c3ca8`.
Only public implementation, public reference applications, and the approved
product-neutral requirements are sources. Do not access or change the private
workroom. MANIFESTO and BRAND are unchanged.

This is an intentional execution-semantics change within format 1, not a claim
of backward-compatible behavior. Current specifications below supersede earlier
fail-fast defaults in historical task specifications and acceptance reports;
those historical records remain unchanged. Existing byte hashes prove unchanged
declarations, not unchanged engine semantics or renewed human approval. Consumers
must review the changed behavior and pin the engine used for their evidence.
This task does not introduce format 2, a second execution engine, multi-user
execution, deeper inclusion, automatic retry, or guaranteed cleanup.

## Purpose and expression

Collect subsequent declared checks when an action completed but its assertions
failed. Preserve every failure and make dependent nonexecution visible. Do not
infer whether later failures are caused by earlier ones; that judgment belongs
to the scenario author. This mechanism does not prove adoption value or savings.

Keep the approved `steps` / `do` / `expect` structure. An ordinary leaf step may
add `on_failure: stop`. Omission means continue after FAILED. The only accepted
explicit authored value is the literal string `stop`; reject null, booleans,
other strings, mappings, references, and unknown policy fields. Include-call
nodes still accept only their existing fields and cannot override child policy.
No assertion or action changes its meaning, including exact HTTP-status checks.

## Execution decisions

| Outcome | Current step | Later steps in this projection |
| --- | --- | --- |
| All checks pass, or an assertion-free action completes | PASSED / COMPLETED | Continue |
| Ordinary checks fail, default policy | FAILED | Continue |
| Checks fail with `on_failure: stop` | FAILED | All remaining leaves BLOCKED |
| A response-derived value is missing, null, or invalid for its use site | BLOCKED, before action | Independent later leaves may run |
| Execution, port, normalization, integrity, session, or unknown exception | ERROR | All remaining leaves BLOCKED |
| Explicit adapter skip or poll SKIP timeout | SKIPPED | All remaining leaves BLOCKED |
| Poll FAIL timeout with last response | FAILED | Continue unless explicit stop |

All execution ERROR and SKIPPED outcomes retain conservative stopping behavior
in this first slice. Do not guess recoverability from exception messages. No
401/403 automatically means a broken session: it remains an observed response
subject to the declared checks. Stopping one projection does not suppress other
selected projections in the runner.

### References and local dependency blocking

Availability is not synonymous with a passing source step. A trustworthy actual
normalized response from a FAILED step remains referenceable. A missing source,
missing field, null field, or response-derived value that cannot occupy the
declared path/value/check position blocks the consumer, with zero action, permit,
request, or mock consumption. Preparation remains atomic and its diagnostic
binding map is empty if it does not complete. Other independent later steps can
run; a consumer of a locally blocked step is itself locally blocked. A local
BLOCKED is not an assertion failure, so `on_failure: stop` does not promote it to
a global stop. The report must expose the direct unavailable source step(s).

Use a dedicated internal dependency-unavailable condition. Do not reinterpret
arbitrary ValueError/KeyError, invalid authored literals or parameters, malformed
normalizer output, or port errors as recoverable dependencies. Existing strict
declaration validation still runs. After complete preparation, subsequent ERROR
preserves the existing sensitive shallow-copy binding diagnostic.

### Polling, mocks, and inclusion

Poll FAIL may expose the last actual normalized response, not a fabricated ready
response. Its producer and any consumer reference must identify source step,
attempt number, non-final status, and timeout provenance without embedding values.
Existing recordings remain `is_final=False` on timeout. Contract continues to use
only final recordings and may therefore report missing evidence; do not relabel
timeout records to make it pass. SKIP still stops this slice.

Frontend mock responses retain ordered consumption by real traffic. A BLOCKED
step does not consume, discard, reorder, or reserve a mock entry. A later actual
request must match the next unconsumed entry or produce the existing protocol
ERROR. Continuation is not permission to repair mock plans or evidence identity.

One-level, same-actor include remains deterministic flattening. Each child leaf
retains its policy and qualified step ID; named results can refer to trustworthy
responses from failed child leaves. An explicit child stop blocks all later child
and parent leaves in the projection. Parent code cannot override child policy.
The expansion review view displays the effective failure policy; impact inspection
detects an authored policy addition/removal/change. Sidecar pin rules are unchanged.

## Reports and compatibility

Add defaulted keyword-only metadata, preserving existing positional construction:

- `after_failures`: ordered qualified IDs of earlier FAILED leaves, attached to
  subsequent actually executed steps, including assertion-free actions.
- `blocked_by`: source IDs responsible for dependency blocking or the stopping
  step for globally blocked leaves; no actual data values.
- response-origin and binding-source metadata: producer ID, attempt index,
  final/non-final flag, and timeout marker, sufficient to distinguish a consumer
  of a timed-out response from a consumer of ready evidence. The implementation
  must document its exact field shape in SCENARIO.md and test it.

Do not add runtime values, credentials, sessions, body dumps, or new automatic
serialization. Preserve `resolved_bindings` sensitivity, top-level isolation,
repr/equality rules, and the warning about third-party/asdict serialization.
New dependency diagnostics name locations, not sensitive offending values.

Any FAILED/ERROR keeps the domain/run FAILED. A domain with BLOCKED but no
failure is DEGRADED, never PASSED, even when another check succeeded; degradation
inspection must expose nonexecution. Existing `localize()` tuple shape remains
unchanged. The sole strict acceptance gate remains `status == "PASSED"`; do not
change the older convenience `passed` property in this task.

## Required implementation and verification

1. Strict declaration positive/negative tests, version 1 only, no include-level
   policy, and policy visibility through expansion and impact inspection.
2. Backend default FAILED continuation and explicit stop; errors and SKIP still
   stop; waits/assertion-free steps receive prior-failure metadata; runner keeps
   projections independent. Invalid response evidence must not become PASSED.
3. Atomic missing/null/invalid-use references, false/zero/empty valid neighbors,
   dependency chains and unrelated continuation; unexpected exceptions remain
   ERROR. Cover nested body/check references and included parameter substitution.
4. Poll success, FAIL continuation, FAIL stop and SKIP stopping, correct last
   attempt provenance on producer/consumer, unchanged non-final recording and
   honest contract missing-evidence result.
5. Shared UI loop: frontend mock, live e2e, explicit API, and request-free actions;
   one context closed once, no action/permit/mock consumption when BLOCKED,
   ordered fixtures never silently skipped, and all identity/replay protections.
6. One-level included leaf default continuation, child explicit global stop,
   named-result reuse after FAILED, qualified metadata, and unchanged actor/depth
   rejection. No API requiring callers to inspect child internals is introduced.
7. Report aggregation, isolated BLOCKED, localize/degradations, constructor
   compatibility, independent defaults, and sensitive repr/nonserialization.
8. A runnable public Documents example: create, list/search, delete. Execute
   unchanged assertions against normal responses, wrong-title response with
   valid ID, and wrong persisted title: collect subsequent checks and actually
   delete when mechanically possible; preserve FAILED overall. Test explicit
   stop and missing-ID neighbors. Reuse existing adapter/routes, not product fixes.
9. Actual Demo Chromium mock/live continuation after first assertion failure,
   plus stopping comparison, with real second-action traffic and no skip.
10. Update current documentation and current runtime expectations according to
    test intent, not blanket replacement of ERROR or adding stop everywhere.
    Preserve historical fault snapshots, frozen harnesses, review fixtures/pins,
    and old acceptance records. Compare fixed faults by detection, not equality
    to historical fail-fast action counts or subsequent BLOCKED states.

Focused tests must demonstrate the baseline's rejected policy or fail-fast
behavior before implementation, then pass after it. Run full tests, real Chromium,
an isolated dev-only core suite, maintained Scenario and documentation examples,
lock, hygiene, and diff/cached-diff checks. Independent audit reviews code and
additional counterexamples. Record actual commands/results, scope, and limitations
in a public English acceptance report; no private details or unmeasured claims.

## Stop point

Local architect acceptance ends this task. Report the schema-1 sample decision,
new capabilities and conservative stopping boundaries to the maintainer. Leave
all accepted changes unstaged, uncommitted, and unpushed; the workroom is untouched.
