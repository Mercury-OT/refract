# Bounded native-await browser request association

Status: specification and evidence boundary approved by the maintainer on
2026-10-30. Feasibility comes first; implementation is authorized only if the
association method survives the controls below. Independent audit and architect
acceptance precede the authorized submission, PR checks, merge and main checks.
Starting main: `a14965a`. No Scenario expression changes are authorized.
Independent audits and local architect acceptance subsequently passed; see the
[measured results and closed findings](browser-native-await-acceptance.md).
The associated task PR records submission and hosted delivery checks.

## Problem and scope

The existing neutral multi-origin consumer has ten identical Scenarios for two
frontend implementations. Nine native-async cases send real HTTP but lack action
association after `await`; the registered-Promise implementation passes. Waiting
for a handler's completion is already supported and is not proof of request
ownership. This task tests whether Chromium can provide sufficiently precise
association without changing the target or declaration.

Limit the candidate to the opt-in native multi-origin collector and supported
trusted click/input handlers: one or more native awaits, including an awaited
async helper, followed by fetch or asynchronous XHR. Keep the existing action,
user, session, context, request and response identities, bounds and statuses.
Format 1, one-level include, vocabulary and all existing YAML remain unchanged.
Public sources are existing synthetic application code, browser tests and
browser protocol behavior. No private repository or evidence is an input.

## Feasibility gate

Before production implementation, run actual Chromium/HTTP probes. A candidate
may use a per-invocation marker and browser-provided async execution relationships.
These are hypotheses to test, not assumed causal guarantees. A common function,
source location, URL, body, expected response, time window, or merely finding an
ancestor marker does not prove ownership. A promise's producer must not be
mistaken for each consumer; several waiters and repeated callbacks must remain
distinct. No application-source rewrite, conversion of await to then, private
wire marker, replay, debugger stepping, or global active-action inference.

Required controls before implementation:

1. Sync, explicit then, single/multiple await, nested awaited helper and XHR.
2. Identical requests from current action and background work, including the same
   helper and shared promises with independent consumers.
3. Timers started inside an action, detached work, prior-step late requests and
   repeated invocations of the same handler. A background timer is not promoted
   merely because it was scheduled while an action was active.
4. Missing, truncated, contradictory or ambiguous browser relationships retain
   unavailable/diagnostic evidence; required checks cannot pass from that data.

If no bounded candidate establishes these distinctions, stop production changes
and deliver the reproducible blocker plus limitations. Do not broaden to a
general JavaScript execution tracker or weaken the ownership requirement.

### Feasibility decision

Two independent actual-Chromium probe sets passed the causal-origin gate on
2026-10-30. Proceed with computed invocation markers and native async stacks,
not JavaScript Error.stack parsing or an async replacement for every handler.
The latter would change synchronous handler return semantics.

Use the nearest exact invocation marker, including a null-origin barrier for an
untrusted callback. Traverse only explicitly tested await/Promise.then transitions
within bounded retained stacks; stop at timer/unknown edges, absent markers or
truncation. A synthetic event must not inherit the trusted outer event's marker.
Collection requests at most 32 async parents. Parsing permits at most 128 frames
per stack, 1024 frames in total and 4096 characters per function name; excess
input supplies no origin. External parent IDs are not fetched. Chromium's
`Debugger.setAsyncCallStackDepth` provides bounded observations, not a guarantee
of complete causality. Disable breakpoints and request skipping all pauses;
initial/repeated navigation and product `debugger` statements must not introduce
an unbounded pause. These controls set no breakpoint and perform no stepping.

Ownership and completion are separate, as in the existing registered-Promise
path. A detached async helper directly invoked by an action can retain that
action's causal identity; this does not prove the handler awaited it or create
an additional completion barrier. A later arrival must retain its old identity
and cannot satisfy a subsequent step. Independently scheduled background work,
including other consumers of the same promise, cannot inherit that identity.
The helper continues to wait only for its existing returned-handler promises
and bounded associated request completion. No global network-idle rule is added.

Post-await fetches initially have no synchronous JavaScript origin. Retain at
most 128 unresolved local fetch handles until the native collector classifies
their exact request marker. Before delivery, the collector claims only the
proven origin. Background handles retire on fetch settlement/rejection without
a synchronous collector call. An early response callback then
clones/drains only a claimed response using the existing 8 MiB/deadline bounds,
without consuming or replacing the application's original response. Missing or
overflowed handles for associated requests are errors, never successful evidence.
Resolve/reject removes handles; context closure releases the remaining page state.
No background body is drained to manufacture evidence. This is local completion
bookkeeping, not a new declaration, port, wire marker or inference from values.
Continuous background traffic under simulated slow protocol communication must
not starve foreground completion; a regression test uses a separate process with
an external bound. The ordinary action deadline is not an operating-system-level
preemption guarantee for a blocked renderer or protocol call.

## Implementation and acceptance, conditional on the gate

Preserve native CORS/preflight, separate credential destinations, request counts,
raw headers/body ownership, live/mock isolation and existing deadlines. No new
polling or global network-idle wait, no new ports or report state, no expectation access by the
collector. Late results and user/session/context changes must not cross identities.
Incomplete collection remains visible through existing failure paths.

Keep the existing ten Scenario files, both consumer implementations and adapter
unchanged. Run all twenty units against the baseline and candidate; no case can
be removed from the denominator. The intended candidate result is ten passes for
each implementation, with negative controls still rejected. Repeat the fixed
maintenance variant and complete panel without claiming general reliability or
measured human savings. Missing-association results remain honest if blocked.

Independent audit must review the mechanism, exercise its adversarial controls,
and verify frozen consumer inputs. If code changes, run the full suite including
actual Chromium, dev-only core checks, litmus/documentation sentinels, lock,
repository hygiene and diff checks. Verify no changes to YAML, core vocabulary,
dependencies or CI. Review public information sources before submission.

## Deliverables and non-goals

Deliver this specification, reproducible feasibility probes and results, and
either bounded implementation/tests with acceptance evidence or a blocker record.
Update the relevant guide and roadmap facts only; historical measurements remain
historical. Do not claim broad async support from a passing finite panel.

No timer-origin expansion, streaming transports, workers, redirects, popup/frame
flows, new UI actions, dynamic targets, Flow, workbench, database changes, new
declaration syntax, private adapters or private evidence. A missing association
is not a reason to ask a product to change its implementation for the test tool.
