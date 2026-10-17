# Response-based rejection evidence

## Authority and scope

On 2026-10-17 the maintainer approved the four-step `documents.owner_access`
example and its evidence limits, then authorized specification, development,
independent audit, and architect acceptance. Public submission is explicitly
authorized only after those gates pass. Use the dedicated task branch and PR
workflow; do not bypass CI. Starting main is
`b2fdab2bc1092433eef0baa684c44cefbf665a97`.

Sources are the existing public Documents application and adapter, current
declaration/report implementations, and the approved neutral example. Public
text stays English. No private workspace is accessed or changed. No private
product information, local paths, credentials, or adoption measurements enter
this task. MANIFESTO, BRAND, runtime core, adapters, target application, dependency
locks, and CI configuration are outside the change scope.

## Purpose and non-claims

Make a maintained example distinguish an explicit object-ownership rejection
from an invalid session, invalid input, an unspecified refusal, and a refusal
for a different reason. Existing `status_equals`, `failure`, and `field_equals`
already express the required observations. This is an example, documentation,
and negative-control task, not a new rejection taxonomy or capability API.

A response code is the target's stated reason. It does not independently prove
that the corresponding internal decision point executed correctly. A successful
profile check is evidence about that request, not a guarantee that a later
request's session remains valid. Contract uses the same backend recordings and
normalizer; it is not an independent witness. No UI or real-product security
claim follows from these offline synthetic checks.

## Frozen example

Add `examples/documents/scenarios/owner_access.yaml`, preserving the approved
structure and values. English comments may explain the expression. Keep format
1, `users: [creator, peer]`, and parameter
`document_title: Permission review document`.

1. `create`, user `creator`, `on_failure: stop`: POST `[documents]`, body title
   from that parameter and category `guide`. Require status 201, success,
   `has(document_id)`, and title equal to the parameter.
2. `creator_reads`, user `creator`, `on_failure: stop`: GET `[documents,
   {from_step: create, response_field: document_id}]`. Require status 200,
   success, and document_id equal to the actual creation response ID.
3. `peer_profile`, user `peer`, `on_failure: stop`: GET `[account, profile]`.
   Require status 200 and success.
4. `peer_reads`, user `peer`: GET the same creation-derived document path.
   Require status 403, failure, and `field_equals` on `error_code` with literal
   `owner_required`. Reuse the current session; do not add `session: new`.

The scenario ID is `documents.owner_access`. No include, role declaration,
polling, state assertion, or additional operation is introduced into this
approved example. Existing inclusion, named results, and the prior owner/peer
example remain unchanged.

## Evidence and reporting contract

- Read `error_code` from the existing normalizer's extraction of actual
  `fault.code`; never infer ownership from 403 or manufacture a missing reason.
- Wrong or absent required reason produces a failed check and FAILED run, not a
  new UNVERIFIED state. Explain insufficient evidence without asserting that an
  access-control vulnerability has been established.
- Invalid-session/input responses are ordinary assertion failures. The three
  prerequisite steps explicitly stop subsequent actions when they fail.
- An execution exception is ERROR at the step and FAILED at aggregate level;
  later steps are BLOCKED under existing rules. No automatic login retry is
  permitted to conceal the observation.
- If state assertions are separately declared without StateProbe, missing
  capability remains visible as degradation. A probe returning no required
  record fails its assertion; a probe exception is an execution error. Do not
  claim all evidence gaps have one native status.
- Existing span attributes are matched separately over same-named spans; do not
  present several attribute checks as proof of one shared decision event.
- Preserve sensitive default repr boundaries; never publish raw session tokens
  or general report serialization. The strict gate is `report.status ==
  "PASSED"`, not `report.passed`.

## Required tests

Use real `run_scenario`, the real public normalizer/transport, and the synthetic
Documents target. Execute the approved file unchanged with backend plus contract
and with explicit-API e2e. This e2e path is not browser evidence.

1. Normal case passes all steps with actual statuses 201/200/200/403; distinct
   accounts, two authentications, same object ID, same peer session, no extra
   contract requests, and the final reason check actually evaluated.
2. An invalid peer session before profile causes FAILED then BLOCKED without
   executing peer_reads. Invalidation after a successful profile causes the
   final read to fail with actual 401/session_required, with no silent refresh.
3. A bounded request fault causes the target's real input validation to reject
   creation; later steps are blocked and no ownership pass is claimed.
4. Hold actual final status at 403 and normalized failure true while removing
   the fault code, using null, an unknown code, an authentication code, an input
   validation code, or a different authorization code. All fail the reason
   requirement. Include strict wrong-type observations and a passing neighbor.
5. Record fault reachability, requests, actual response content, relevant failed
   checks, and aggregate statuses. Failures in unrelated setup must not count as
   successful detection of a final-response mutation.
6. A temporary weaker declaration omitting only the reason check passes the
   same ambiguous 403 control that the approved declaration rejects. Never
   weaken the maintained example or derive target replies from expectations.
7. Known raw response samples exercise faithful normalizer extraction, including
   missing and malformed reasons; a status alone must not generate a reason.
8. Execution exceptions and separately declared missing state evidence retain
   existing ERROR/BLOCKED and DEGRADED behavior. Sensitive authentication
   material is absent from default report representations.
9. The complete public YAML loads through the real loader; documentation
   fragments, if any, are tested in their declared context. No vocabulary,
   schema version, ports, runtime semantics, or private inputs are changed.

Fault injectors belong in tests, are explicit and bounded, and must exercise the
real pipeline rather than patching evaluators or report statuses. They are not
new target features or a general mutation framework. A second product adapter
is not required: this task adds no core capability and makes only bounded claims
about this public reference consumer. Full regression protects other consumers.

## Delivery and acceptance

Expected public scope: this specification, the new YAML and focused tests, a
short `docs/rejection-evidence.md` guide, a link from SCENARIO.md, the roadmap,
and a local acceptance record. Preserve old historical acceptance records.

Run focused controls, maintained declaration loading, full regression including
real Chromium, an isolated dev-only regression, lock/hygiene/diff checks, and an
independent audit with additional probes. Record commands, actual counts, limits,
and findings. Architect acceptance freezes the exact file list before staging.
The maintainer's current authorization then permits public branch submission,
PR checks, merge, successful main CI verification, and branch cleanup. No
private workspace operations are authorized.
