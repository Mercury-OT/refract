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
| A keyboard operation reaches another input, or unrelated traffic is reported as its result. | **Bounded Enter contract:** explicit driver capability, signed key, unique already-focused input, trusted dispatch guards, observed down/up receipt, and existing action-origin request capture. Synthetic nested events cannot borrow the outer key callback; focus displacement invalidates the action. Same-page form support additionally pins the actual form/default submitter and isolates programmatic submission scopes; a trusted submit event alone is insufficient. | No automatic focus repair, native form-navigation support, hostile-page attestation or rollback of product effects before a late error. Product code must cancel its own submission; an implicit-button click is not submit-handler request evidence. A custom adapter's receipt is a checked claim, not independent proof. |
| Hover is omitted, reaches a different element, or its background work is mistaken for a later click. | **Bounded hover contract:** explicit capability, pinned unique visible main-document target, trusted movement at an unobscured in-viewport point, final identity/hit checks and an owned strict receipt. Hover callback origins are null; page assertions remain separate from delivery. | No scrolling, hidden click/focus/style repair, guarantee of a new enter event, hover request association, hostile-page attestation or rollback. A custom receipt remains a checked adapter claim; the initial-hidden and revealed-menu checks prove only their declared page observations. |
| An object-specific click targets the wrong row or a legacy adapter ignores its ID. | **Object-selection contract:** explicit capability, signed object_id, strict actual-selection receipt, owned report copy; the browser helper checks unique row/control identity again at trusted click dispatch. | No independent attestation of an adapter's identity mapping, hostile-page sandbox, hidden object lookup, or rollback of pointer/hover effects before click. Missing product identity remains an evidence gap. |
| Document replacement loses an actual selection or substitutes an unrelated navigation. | **Bounded same-tab navigation:** old-document receipt ownership, source execution-context identity, native navigation observation and one matching main-frame request/committed loader. New-document startup traffic remains background. | No causal inference from matching URLs, no support for arbitrary deferred navigation, and no proof that the destination represents the correct business object without its declared checks. The page-world bridge is not resistant to malicious same-world code. |
| A background request or another API origin is mistaken for the current browser action. | **Bounded multi-origin contract:** native initiator/network identities, exact nearest callback scope through supported bounded async ancestry, disjoint configured logical prefixes, origin metadata, current permit/session pairing and replay checks. Null callback scopes and unsupported async edges are barriers; no URL, content or time-window inference. | Chromium-local association is not proof of independent server instrumentation or awaited completion. Missing/unsupported ancestry remains diagnostic; late work cannot become a later action's evidence. |
| Allowing an API or static resource also exposes credentials or bypasses browser security. | **Bounded multi-origin contract:** separate connection and credential destination rules, rejection before unauthorized delivery, native networking/CORS, no request replay or inferred permissive response headers. | Not an egress sandbox for arbitrary adapter code, hostile browser scripts, all authentication schemes, streaming transports or compromised collectors. |
| Simulated responses are mistaken for real target behavior. | **Existing and regression-tested through migration:** explicit fixtures, mock/live separation, consumption checks and no live fallback. | A mock pass is not evidence of the live target; fixtures may share values with expectations but cannot be manufactured from them. |
| Normalization selects the wrong field/object or conceals a failure. | **Existing:** bounded result-type and protected-evidence checks. The [fixed mapping panel](tasks/mapping-fidelity-acceptance.md) demonstrates separate sample checks detecting stale or invented fields even when Scenario execution passes. These are tests, not an automatic runtime mapping gate. | No universal validation of every transformation or adapter-supplied raw response. Meaningful normalization is allowed; missing observations may not be invented. Selected cooperative in-process samples are not independent external evidence. |
| Content identity or repeated observations are mistaken for approval or independence. | **Existing documented boundary:** include hashes pin bytes; report sources and shared dependencies must be interpreted explicitly. | Hashes do not approve content; multiple projections or AI reviewers do not automatically provide independent evidence. |
| An API response is mistaken for committed storage, or a state reader selects facts using expectations. | **Object-state boundary:** a separate read-only probe receives only object selectors and execution identity; core checks its returned facts. The synthetic SQLite consumer uses a separate read-only connection, with an uncommitted-write control. | A query echo or source label does not authenticate the database or adapter. Matching current state does not prove its causal history, future durability, or a cross-object transaction. Other databases and production services require their own integration evidence. |
| A green execution is interpreted as complete business correctness or release authorization. | **Existing:** explicit execution states, strict PASSED gate, and separate review/publication decisions. | No proof of complete Scenario coverage or fidelity to all human intent; no automatic release authorization. |

An actually observed missing field or expected refusal can be ordinary evidence:
the declared check decides pass/fail. Acquisition failure, malformed evidence,
and unavailable dependencies keep their existing distinct handling. Do not add
a universal rule that empty, false, null, or non-success HTTP responses must make
every Scenario fail. Preserve valid negative scenarios and visible evidence gaps.

The bounded Escape extension reuses the key receipt and requires the same input
and focus throughout collection. Escape callbacks have no request-evidence origin;
page checks separately establish dismissal and retained text. A synthetic event
can change a page but cannot substitute for the actual down/up receipt. This is
not a guarantee for dialogs that move focus, nor hostile-page attestation.
Unavailable panel association is an error, not false visibility.

New claims of trust or resistance to fabrication must identify their threat,
controlled boundary, and verification. Deliberately hostile in-process code,
compromised collectors, and adversarial AI scoring require separately designed
execution/collection controls; this task does not supply them. Approval records
and source labels cannot substitute for those controls.
