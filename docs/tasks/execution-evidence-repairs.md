# Execution evidence classification and bounded browser collection

Status: approved for implementation, independent audit, architect acceptance and
subsequent task-branch delivery on 2026-11-08. Starting main: `b3a828b`.
Submission follows acceptance, green PR checks, merge, green main CI and cleanup.
Implementation, independent review and architect acceptance passed on 2026-11-09;
see the [verification record](execution-evidence-repairs-acceptance.md).
Sources are public code and neutral local reproductions, not private products,
workspaces or external test corpora. This is a finite repair, not new capability.

## Verified findings and decisions

1. After hover or Escape, the browser helper deliberately blocks unassociated
   mock API requests for the remaining context lifetime. A subsequent open can
   need such a request, and its page check then fails because of our intervention.
   Keep isolation, but report the intervention as a step ERROR, not a product
   assertion FAILED or a successful observation with a diagnostic footnote.
2. DomainResult, RunReport and FlowReport currently accept DEGRADED in passed.
   Change all three properties to exactly status == PASSED. Preserve aggregation,
   execution, continuation and Flow publication rules. This is a documented Python
   API tightening; no permissive replacement or new status is introduced.
3. Backend accepts StateProbe facts without checking their exact type or trace
   identity, unlike live UI. Reuse a shared, owned validation path across both,
   including polling and the final observation after timeout. Missing or invalid
   correlation is ERROR; absent probe remains visible degradation; valid complete
   evidence that does not satisfy the check remains FAILED. Preserve the existing
   API request trace fallback; never invent observed browser/server trace data.
4. Native background diagnostics reserve their count after a reentrant protocol
   call. Slow-reader experiments retained 100 records but performed 133 body reads;
   a separate slower control exceeded the collection deadline. Reserve work before
   yielding, bound optional diagnostic work and preserve foreground evidence.
   The local experiments do not establish a particular low-CPU failure frequency.
5. Browser failures lose their specific safe reason at both helper and core
   boundaries. Carry a finite reason category, not raw exception text, through
   both layers. Retain primary failure information if owned cleanup also fails.
6. Uncaught page exceptions are currently a global, sticky context error, including
   unrelated timers and unhandled rejections. Preserve this conservative policy
   and describe it accurately. A page error is not proof that the current action's
   handler failed. console.error alone remains nonfatal. Error-origin inference or
   a new configuration to ignore page exceptions is outside this repair.

## Failure and ownership contract

The existing step ERROR subsequently blocks work according to current execution
rules; aggregate Domain/Run status can remain FAILED. No new report status,
automatic focus/session repair, fallback fixture or guessed request association.
Only an actual helper-initiated mock block creates the new hard failure. Ordinary
unassociated native connection failure and diagnostic truncation remain diagnostics;
legacy acquisition failures retain their existing error behavior.
Do not promote every not_checked note to an error. A blocked request must never
consume a fixture or reach live API services, including late requests and retained
Flow contexts. Do not reset quarantine on navigation to make a case pass.

Safe categories are a finite shared action-error contract, with no dependency
from core on the optional browser package: collection_timeout, page_error,
policy_denied, target_unavailable, evidence_invalid, mock_background_blocked,
collection_failed and cleanup_failed. An exact validated category may reach the
report; arbitrary exception names, strings, messages, stack values and mutated or
unknown category objects may not. Keep the existing generic built-in classification
for other adapter exceptions. This improves diagnostics, not hostile-code security.

State validation checks exact StateFacts type and exact current trace identity,
then retains an owned copy. No request value, observed span or actual trace enters
the error text. No state expectation means no probe call. A correct request-side
trace without a server echo remains a supported correlation context, not proof of
server participation. A mismatched response trace must not select another request's
state. Keep object-state observation and assertion meanings unchanged.

## Bounded collection and verification

Count optional diagnostic retrieval attempts before any protocol call can process
another event; include pending work in limits and prevent duplicate retrieval.
Bound retained bytes and records as before, and make diagnostic truncation visible.
Do not wait for all background traffic to stop. Associated responses still need
complete actual identity, body and header evidence. Origin, credential, CORS and
redirect policy checks remain mandatory. Mock consumption is exact and must not
use a live-diagnostics truncation shortcut. Preserve external bounded cleanup.

Use deterministic reentrant protocol controls and real Chromium slow-reader
controls to distinguish collection work from host timing noise. Separate browser
startup/cleanup and combined-test duration from each production action budget.
Do not repair the issue solely by increasing production timeouts or deleting the
pressure tests. An action that truly exceeds its deadline still fails safely.

## Acceptance matrix

| Area | Positive and negative controls |
| --- | --- |
| Strict passed | All three report levels: PASSED true; DEGRADED, FAILED, EMPTY and applicable NOT_SELECTED false. Missing create ID blocks read with no request, and Flow stop/continue/publication rules stay intact. |
| State correlation | Correct facts pass; wrong/missing/empty/wrong-type trace and lookalike facts error. Exercise backend, e2e, ordinary/polling/final read; absent probe degrades, valid nonmatching facts fail after bounded waiting. |
| Mock intervention | Legacy/native, hover/Escape, subsequent open and retained Flow context: ERROR, no fixture consumption/live fallback; clean mock/live controls still pass; late work cannot become current evidence. |
| Diagnostic budget | Reentrant unit control and slow real browser control bound actual reads, not just retained records; one real associated foreground request remains exact while background traffic continues. |
| Safe reasons | Actual timeout, page exception, policy denial, target failure, invalid evidence and cleanup failure preserve fixed reasons through RunReport; sensitive values and arbitrary exception class names never appear. |
| Page policy | Unrelated uncaught throw/rejection errors remain visible; console.error and clean page controls pass. No claim of action ownership for global errors. |
| Regression | Existing UI, navigation, keys, sessions, Flow, include, mock, policy and privacy controls; full real-browser suite, supported dev-only Python versions, litmus, docs, lock, hygiene and diff checks. |

Preserve schema_version 1, current YAML bytes and one-level inclusion. No vocabulary,
dependency, product, Flow shape or assertion expansion. Object absence remains
paused. Public docs explain the Python migration and browser limitations; historical
acceptance records retain their original results. Independent audit challenges
the implementation before acceptance. Report actual results and any residual
performance uncertainty without claiming universal browser support or adoption gain.
