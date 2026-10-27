# Evidence and adapter trust boundaries

Approved scope, 2026-10-27, accompanying the
[action-port boundary task](tasks/action-port-boundary.md). Input isolation has
passed independent audit and local architect acceptance; see the
[verification record](tasks/action-port-boundary-acceptance.md). This page adds
no runtime or report state. Hosted delivery remains a separate gate.

The integration assumes adapters cooperate with their declared contracts but
may make mistakes. Core checks declarations and supplied observations. It does
not independently establish that every observation occurred in the target.
The implemented boundary reduces unnecessary expectation access and shared-data
mutation; it is not a Python sandbox or adversarial adapter certification.

| Risk | Mechanism and status | What it does not establish |
| --- | --- | --- |
| An operation reads expectations and fills or selects evidence to match them. | **Implemented and tested:** action-only request/UI inputs, removal of full declarations and unrelated resolved bindings, signature plus actual-argument tests. | No protection against an adapter reading files, globals or process memory. Necessary action values can legitimately equal expected values. |
| An adapter accidentally changes a future check or retained result through a shared container. | **Implemented and tested:** owned request/action data, validated returned-request snapshots, and mutation probes. **Existing:** selected request/recording checks and normalization snapshots are preserved. | No blanket immutability of the interpreter or external handles; credentials, browser contexts and the mock cursor retain explicit ownership/lifecycle rules. |
| A wrong request or stale observation is used for the current operation. | **Existing:** request comparisons, permit and step/user/session/trace correlation, replay and recording checks. | Matching identities, HMACs and trace headers are local consistency mechanisms, not independent proof that a real external event happened. |
| Simulated responses are mistaken for real target behavior. | **Existing and regression-tested through migration:** explicit fixtures, mock/live separation, consumption checks and no live fallback. | A mock pass is not evidence of the live target; fixtures may share values with expectations but cannot be manufactured from them. |
| Normalization selects the wrong field/object or conceals a failure. | **Existing:** bounded result-type and protected-evidence checks. Mapping-fidelity examples remain a separate planned evaluation. | No universal validation of every transformation or adapter-supplied raw response. Meaningful normalization is allowed; missing observations may not be invented. |
| Content identity or repeated observations are mistaken for approval or independence. | **Existing documented boundary:** include hashes pin bytes; report sources and shared dependencies must be interpreted explicitly. | Hashes do not approve content; multiple projections or AI reviewers do not automatically provide independent evidence. |
| A green execution is interpreted as complete business correctness or release authorization. | **Existing:** explicit execution states, strict PASSED gate, and separate review/publication decisions. | No proof of complete Scenario coverage or fidelity to all human intent; no automatic release authorization. |

An actually observed missing field or expected refusal can be ordinary evidence:
the declared check decides pass/fail. Acquisition failure, malformed evidence,
and unavailable dependencies keep their existing distinct handling. Do not add
a universal rule that empty, false, null, or non-success HTTP responses must make
every Scenario fail. Preserve valid negative scenarios and visible evidence gaps.

New claims of trust or resistance to fabrication must identify their threat,
controlled boundary, and verification. Deliberately hostile in-process code,
compromised collectors, and adversarial AI scoring require separately designed
execution/collection controls; this task does not supply them. Approval records
and source labels cannot substitute for those controls.
