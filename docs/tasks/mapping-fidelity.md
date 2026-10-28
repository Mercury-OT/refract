# Mapping fidelity and discoverable counterexamples

## Authority and scope

Approved bounded task, 2026-10-28, starting at public main `ee4691e`.
The maintainer authorized specification, implementation, independent audit and
architect acceptance, followed by task-branch submission, green PR checks,
merge, green main checks and cleanup. No private workspace access is authorized.
Sources are public code and the maintainer's approved neutral scope.

Development, independent audit and local architect acceptance subsequently
passed on 2026-10-28; see the [bounded results](mapping-fidelity-acceptance.md).
The task PR records the separately authorized publication checks.

This is a finite verification exercise, not a new adapter capability. Keep all
core, production adapters, target applications, maintained Scenario and pin
files, dependencies and CI unchanged. Preserve format 1 and one-level inclusion.
Do not introduce a mapping DSL, assertion vocabulary, report status, conformance
platform, database evidence, Flow implementation or broader mutation campaign.
An unexpected runtime defect is reported separately, not automatically repaired
by expanding this task.

## Question and existing evidence

Can a small, independently specified sample check expose a mapping error that
ordinary Scenario execution may miss? Use the existing Documents
`dictionary_document_reference.yaml` create/read flow, with backend only.
The target is an actual stateful in-process synthetic service. These runs do not
establish HTTP-network, browser, real-product or adoption evidence.

Reuse, rather than rebuild, these existing controls:

- `test_member_reference_consumers.py`: actual object identity and route use.
- `test_field_comparison_consumers.py`: complete content, missing/malformed
  observations, unauthorized mutation, and weak/strong checks.
- `test_rejection_evidence.py`: raw rejection reasons and weak/strong checks.
- `test_header_documents.py`: actual duplicate creation and request evidence.
- The frozen stabilization panel: target faults and reachability controls.

Historical measurements and fixtures remain unchanged. This exercise does not
produce an overall detection rate or repeat the historical campaign.

## Fixed panel

Use at most these four fault classes. Normal neighbors are controls, not extra
fault classes. All faulty adapters and target wrappers live only in tests.

| ID | Fault | Required observations |
| --- | --- | --- |
| M1 | Resolver reads a different existing document. | Explicit setup creates the unrelated document; the flow creates its own document. Record the actual two identities and GET target. The normal resolver reaches the created identity; the faulty resolver does not. Do not count a 404 or an unreached injection as detection. |
| M2 | Normalizer reuses the previous title. | A fixed two-response sample has different observed titles. Separately run a target whose read title differs from create: the honest adapter exposes the failed assertion; the stale adapter may hide it. Record this latter run as a combined target/adapter fault. |
| M3 | Normalizer invents a missing title. | Fixed observed data omits title; the expected normalized fields omit it. Separately exercise the same absence during read. The honest adapter must not synthesize evidence; a fabricated title can make the Scenario pass while the mapping check fails. |
| M4 | Scenario omits its read-title check. | A temporary copy removes exactly that assertion. Against the changed-title target, compare strong and weak declarations with identical observations. This is a missing obligation, not an adapter defect. |

If existing tests already establish a row completely, cite and rerun them rather
than adding a duplicate. Reuse existing strict-type tests; do not add unrelated
boolean/integer business cases just to increase coverage.

## Oracle and evidence rules

1. Write small, literal raw-response and expected-field samples before testing
   the faulty normalizers. Expected values are manually specified from the
   documented neutral mapping contract, never obtained by calling the tested
   normalizer/resolver or by using a Scenario pass as an oracle.
2. Legitimate normalization changes shape and names. This is a selected mapping
   contract, not a requirement that raw and normalized objects be identical.
   For Documents, missing document title stays absent; do not generalize this
   rule to unrelated fields whose documented contract differs.
3. Confirm the injected code actually ran, the intended raw response reached the
   driver, and the normal neighbor passes. Preserve status and raw response in
   faulty normalizers so failure is not merely an unrelated identity violation.
   Capture the input and returned fields from the actual normalization call in
   the run; do not call a stateful normalizer again to reconstruct evidence.
   Check request, status and raw JSON snapshots before and after that call.
4. Keep Scenario outcome and sample-mapping outcome separate. An observed
   `PASSED` with an erroneous adapter must stay `PASSED` in the report, alongside
   the separate failed mapping check. Test-local outcomes add no RunReport state.
5. Record actual failed assertion identity or missing obligation, not just a
   nonzero count. Product-only, adapter-only, combined and weak-declaration
   controls are separately labeled. No product-quality percentage is inferred.
6. Samples and mapping checks remain cooperative same-process tests. They do not
   defeat adversarial Python, certify all mappings, establish an independent
   external witness, or prove that future inputs are covered. Contract is not
   run here; sharing recordings/normalization would not add independent evidence.

## Deliverables and stop condition

- This specification and one focused test module, with samples inline unless a
  separate fixture would materially improve auditability.
- A short acceptance record: fixed panel, actual outcomes, exact tests/commands,
  existing coverage reused, independent audit, limitations and remaining gaps.
- Minimal roadmap/threat-model links reflecting completed verification, without
  promoting paused work or expanding claims.

Stop when the normal controls pass, every fixed fault is reached, mapping and
Scenario outcomes are separately explained, and independent audit is resolved.
A missed counterexample does not authorize a new core feature. Validate with
focused tests, related existing controls, the full sequential suite, core-only
tests, litmus, lock and hygiene checks. Verify unchanged production/Scenario
inputs against the starting commit. Public submission follows final acceptance;
do not stage other work or publish local environment details.
