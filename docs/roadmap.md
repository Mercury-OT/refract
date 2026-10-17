# Public roadmap

This is the single public priority and status index for the tasks listed here.
It is a deliberately bounded plan, not an inventory of every possible feature.
Listing a task is not blanket permission to implement, submit, or release it.

## Document authority

| Document | Responsibility |
| --- | --- |
| [MANIFESTO.md](../MANIFESTO.md) | Principles and long-term vision, not a list of implemented guarantees. |
| [SCENARIO.md](../SCENARIO.md) | The currently implemented declaration and execution contract. |
| This roadmap | Public task priority, status, and links. |
| `docs/tasks/` | Each task's decisions, scope, open implementation decisions, and acceptance requirements. |

A proposed example in a task does not change the supported language. When an
implementation is accepted, its contract, examples, tests, and usage guides must
be updated together. Keep status in this index rather than independently
maintaining it in multiple summaries. Historical records remain historical;
they are not silently rewritten to describe later decisions.

## Current priority

| Order | Task | State | Next gate |
| --- | --- | --- | --- |
| 1 | [Business request headers and response-header checks](tasks/business-http-headers.md) | Implemented; independent audit and architect acceptance passed. See the [local acceptance record](tasks/business-http-headers-acceptance.md). Format 1 and the existing structure retained. | Authorized public delivery uses the PR/CI workflow; preserve the accepted header-evidence boundaries. |
| Delivered | [Mixed anonymous users and included-user mappings](tasks/anonymous-users-inclusion.md) | Delivered through PR #24 in main `0c14865`; see the [local acceptance record](tasks/anonymous-users-inclusion-acceptance.md). Format 1 and one-level inclusion retained. | Preserve user/session isolation and explicit complete mappings. |
| Delivered | [Explicit request query parameters](tasks/request-query-parameters.md) | Delivered through PR #23 in main `68af23a`. Approved five-step example, actual browser query checks, format 1 and existing assertion vocabulary retained. | Preserve the accepted query and evidence boundaries. |
| Delivered | [Response-based rejection evidence](tasks/response-rejection-evidence.md) | Delivered through PR #22 in main `eaca8cb`. Approved four-step example; no new vocabulary or runtime semantics. | Preserve the accepted response-evidence boundary. |
| Delivered | [Scenario users and current sessions](tasks/scenario-users-sessions.md) | Delivered through PR #21 in main `b2fdab2`. Its original single-user child restriction is being extended by the separately approved mixed-user task. | Preserve identity, session, evidence, and one-level boundaries. |
| Delivered | [Continue after assertion failures](tasks/assertion-failure-continuation.md) | Delivered in main `95ba66d`; ordinary assertion failures continue, explicit leaf stop retained. | Preserve the approved execution boundary. |
| Delivered | [Exact HTTP response status assertions](tasks/http-status-assertions.md) | Delivered through PR #19 in main `d2a5ed9`; eight branch/PR checks and four main jobs passed. | Preserve the approved `status_equals` / `status_in` expression. |
| Delivered | [Shared Scenario change-impact review](tasks/scenario-impact-review.md) | Delivered on main in `67ce17f`; current YAML and execution unchanged. | Preserve read-only inspection, pin, and review boundaries. |
| Delivered | [Scenario reuse walkthrough](tasks/scenario-review-exercise.md#follow-up-minimal-reuse-walkthrough) | Delivered in `967af3c`; review-cost comparison remains optional and unmeasured. | Use existing expression; no new language feature implied. |
| Delivered | [Named Scenario results](tasks/scenario-named-results.md) | Delivered on main in `f5d258a`: multiple explicit result names, one-level inclusion. | Measure review friction without expanding the language. |
| Delivered | [Scenario inclusion](tasks/scenario-include.md) | Delivered with named results in `f5d258a`; original same-actor boundary is superseded by the separately approved user/session task. | Preserve one level, pins, and caller-review boundaries. |
| Delivered | [Browser adapter support](tasks/browser-adapter-support.md) | Delivered on main in `9bebfa7`. | Preserve the accepted support and evidence boundaries. |
| Delivered | [Action-oriented Scenario format](tasks/scenario-action-format.md) | Delivered on main in `9900820`; workbench withdrawn. | Preserve the accepted expression and execution contract. |
| Delivered | [Bounded response collection assertions](tasks/response-collection-assertions.md) | Delivered on main in `9900820`. | Preserve bounded matching and evidence semantics. |

The maintainer approved the explicit do.request and polling form, and subsequently
the bounded collection expression. Those two tasks have been delivered on main.
Browser support, inclusion, and named results have subsequently been merged.
The approved expression remains the basis of execution;
implementation convenience must not silently change its meaning.

The accepted header slice checks declared business headers against actual API
and browser observations, and selected response headers against complete raw
pair lists. It preserves duplicates and distinguishes unknown evidence from
absence. The approved retry/read example and a separate Documents consumer catch
duplicate creation even when a defective retry echoes the original ID. Final
regression passed 2405 tests with real Chromium, no skips and one existing warning;
fresh dev-only regression passed 2073 with one optional collection skip. Two
independent findings concerning polling aggregation and observed-header error
privacy were fixed and retested. This is synthetic capability evidence, not
production adoption or universal packet-level capture. The acceptance record
does not substitute for the subsequent PR, merge and hosted CI checks.

The accepted query slice exposes per-request filters and pagination values in
the existing request mapping. Actual browser URLs supply observed evidence;
expectations cannot fill it in. The approved synthetic Documents example and
real Chromium/reference-transport controls passed 179 focused tests plus 33
independent probes. Full regression passed 1784 tests with one existing warning
and no skips; isolated dev-only regression passed 1574 with one optional Demo
collection skip. See the [local acceptance record](tasks/request-query-parameters-acceptance.md).
No adoption claim follows from local acceptance. The query slice was subsequently
delivered through PR #23 in main `68af23a`; its acceptance record remains a
historical record of the pre-submission checks.

The accepted mixed-user slice adds `anonymous` to declared participants and complete
`with_users` mappings for multi-user leaf children. Named and anonymous contexts
must remain isolated, anonymous execution must not authenticate, and child
assertions and session rules must remain unchanged. Public Documents callers
exercise both peer and anonymous refusals under the same pinned child, while
separate exact checks preserve the different 403/401 obligations. This is not
deeper nesting, automatic approval propagation, or evidence of review-cost savings.
Final regression passed 1978 tests with real Chromium, no skips and one existing
warning. Fresh dev-only regression passed 1737 with one optional Demo collection
skip. Independent audit's malformed-parent impact finding was fixed and retested;
there are no unresolved findings. Public submission follows the authorized PR/CI
workflow; the local acceptance record does not claim hosted delivery.

Exact recorded HTTP status is now delivered. It addresses a
publicly reproducible distinction between transport status and normalized
business success. It does not identify why a request was rejected or establish
authorization correctness. Public Demo and Documents examples supply independent
synthetic consumers; no private source material or measurements are included.
The separately approved continuation task now changes ordinary assertion failure
to continue by default, with optional leaf `on_failure: stop`; all execution
errors and skips still stop this first slice. Missing response dependencies
block their consumers, not unrelated steps. The maintainer explicitly retained
`schema_version: 1`: unchanged declarations therefore require review against the
new engine semantics, not a claim of behavioral compatibility. Multi-user work
has been delivered under its separately approved specification. Runtime presentation work is deferred while these expression and
execution boundaries take priority. Each task is introduced with its intended
use cases; changed YAML is shown to the maintainer before submission.

The approved user/session slice now passes 1548 full regression tests with real
Chromium and one existing dependency warning, and 1401 isolated dev-only tests
with the optional Demo collection skipped. Independent audit passed, including
identity and Recorder tampering controls. The public Documents target exercises
actual owner/peer access and permission changes; browser tests separately exercise
context/session isolation. These are synthetic capability checks, not evidence
of real-product adoption. Current YAML and reference adapters are explicitly
migrated; historical measurements are not rewritten. See the
[local acceptance record](tasks/scenario-users-sessions-acceptance.md).
No submission or private Scenario migration is authorized by this local result.
The maintainer subsequently accepted the task and separately authorized its
public submission on 2026-10-17. Historical local acceptance retains its original
pre-submission statements; the task PR supplies publication, merge, and CI
evidence. Private workspaces and private Scenario migration remain out of scope.

The accepted bounded task uses existing response assertions to distinguish
an explicit ownership refusal from invalid sessions, invalid input, and absent
or different refusal reasons. Its four-step public Documents example and
negative controls do not add a rejection taxonomy, change the Scenario language,
or establish independent evidence of an internal authorization decision. See
[response-based rejection evidence](tasks/response-rejection-evidence.md).
Its 57 added controls and 16 additional independent probes passed; full regression
passed 1605 tests with real browser execution, no skips, and one existing warning.
The isolated dev-only suite passed 1458 tests with the optional Demo collection
skipped. See the [local acceptance record](tasks/response-rejection-evidence-acceptance.md).
Submission was explicitly authorized contingent on these gates; local acceptance
does not itself claim that publication or hosted CI has finished.
The task was subsequently delivered through PR #22 in main `eaca8cb`; its local
acceptance record retains the original pre-submission status.

The current query task declares filtering and pagination per request and checks
the query actually emitted by a browser. The approved Documents example creates
three records visibly and follows a response-derived cursor in an explicit
second-page step. Contract remains response compatibility over verified backend
recordings, not an independent query witness. Maintained search declarations
are migrated explicitly; no automatic pagination or new assertion vocabulary
is introduced. Synthetic Documents and Demo coverage cannot establish real-product
adoption. Independent audit and architect acceptance passed before the separately
authorized PR #23 submission. Private-workspace work remains out of scope.

Continuation acceptance passed 1426 full regression tests with real Chromium,
no skips, and one existing dependency warning; the isolated dev-only suite passed
1282 with one optional Demo collection skip. Independent review passed 571
focused checks, including 27 additional probes. Malformed normalizer output and
port/nested-wait timeouts cannot masquerade as ordinary failed assertions.
Current examples remain format 1; historical declarations and measurements were
not rewritten. See the [local acceptance record](tasks/assertion-failure-continuation-acceptance.md).
The maintainer subsequently accepted the task and separately authorized
submission on 2026-10-17. Historical local acceptance retains its pre-submission
statements; the task PR supplies publication, merge, and CI evidence. This does
not authorize expansion into multi-user behavior.

The local status-assertion implementation passed independent audit, 1337 full
regression tests with real Chromium and one existing dependency warning, and
1197 isolated dev-only tests with the optional Demo collection skipped. Public
Documents examples demonstrate 201 creation, empty 204 deletion, and a rejection
whose status alone changes from 422 to 500 while its body is unchanged. These
checks establish the bounded capability, not real-product adoption or rejection
mechanism assurance. See the [acceptance record](tasks/http-status-assertions-acceptance.md).
The maintainer subsequently confirmed `status_equals` and `status_in` and
separately authorized submission on 2026-10-17. Historical local acceptance
retains its pre-submission statements; the task PR supplies publication and CI
evidence. No subsequent execution-policy change is authorized by that submission.

The retained local cutover includes core execution, reference adapters,
maintained examples, and their documentation. On 2026-10-13 the maintainer
requested removal of the authoring workbench, its dedicated tests, and guide.
Frontend/e2e product execution and real-browser product tests remain in scope;
removing an editor does not remove a projection. Post-removal local regression
passed 647 tests with real Chromium execution and no skips; the only warning is
an existing dependency deprecation. These are engineering checks, not evidence
of usability or real-product adoption.

Local acceptance is not a release; the task's PR and CI supply submission evidence.
The cutover intentionally rejects old declarations. Existing non-public adapters,
scenarios, and historical evidence have not been migrated by this task.

Core capability work now takes priority over graphical authoring. The approved
collection task addresses the first-item reduction in the public documents
normalizer: expose the observed collection and keep member selection and
comparison in core. `collection_matching_count` preserves the approved Scenario
structure, evaluates strict same-member matching, rejects malformed evidence,
and is reused by response checks, polling, and contract. The executable contract
and reference example are updated. Independent regression passed 767 tests with
real Chromium execution and one existing dependency warning. A separate isolated
core-only installation passed 744 tests with the optional demo collection skipped.
Target-not-first and changed-target negative controls verify the bounded behavior;
they do not establish real-product adoption value.

A bounded real-use maintenance exercise remains necessary to test authoring,
review, execution, and diagnosis cost after capability changes. Its scope and
evidence require separate approval. Passing demo tests alone will not establish
adoption value, requirement completeness, or low maintenance cost.

Cross-version maintenance work is deferred pending meaningful target changes.
The delivered browser-support task supplies optional reusable browser support:
single-action execution, supported fetch/XHR request association, bounded
collection waits, and owned-resource cleanup. Existing YAML and core ports stay
unchanged. Public Demo code and independent synthetic pages are its sources and
test targets. No private adapter or product evidence is included, and synthetic
test success must not be presented as real-product adoption or maintenance savings.

Browser support acceptance passed 863 regression tests with no skips and one
existing dependency warning, including 81 real-browser support tests. Independent
audit passed 96 browser and offline support checks. An isolated core-only install
passed 759 tests with the optional Demo collection skipped; wheel installation
and lazy imports passed without Playwright. All 11 maintained Scenario files
validated unchanged. The Demo now uses the shared helper, while core files,
ports, declarations, and the Demo application remain unchanged. Supported and
unsupported browser behavior is documented in the [usage guide](browser-support.md).

The bounded Scenario inclusion task was locally accepted and is now delivered: one-level static
composition with identical actors, explicit parameter wiring, and parent-sidecar
content pins. The child executes in the current run; a pin is not proof of human
approval, and child review does not approve arbitrary caller arguments or whole
parent requirements. Public demo controls compare included and independently
authored flat flows. Final regression passed 1009 tests with real Chromium and
one existing dependency warning; the isolated dev-only environment passed 896
tests with optional Demo collection skipped. Independent audit passed, including
runtime value-use checks and failure blocking. All three frozen backend faults
were detected by baseline flat, candidate flat, and candidate include controls.
See the [local acceptance record](tasks/scenario-include-acceptance.md) for commands,
file scope, observations, and limits. Human review-cost improvements remain
unmeasured. Inclusion and named results were delivered together through PR #16
in main commit `f5d258aa68af64c7792b7e09d583292fd482788c`. All eight branch/PR
checks and all four post-merge main jobs passed. Historical local acceptance
records retain their original pre-submission status.

The subsequent named-results slice is also delivered. Children explicitly
name observed response fields under `results`; callers use `result` and no longer
depend on child-internal step names. It compiles into the same response bindings,
with no extra runtime call layer or new adapter/port behavior. One-level,
same-actor, exact sidecar pinning remains. A child internal rename still changes
its pin even when caller YAML stays unchanged. Full regression passed 1101 tests
with real Chromium and one existing dependency warning; isolated core-only
verification passed 987 tests with optional Demo collection skipped. Independent
audit passed 228 focused and 10 real Demo tests, plus adversarial probes. The
three fixed backend faults and their passing neighbors retain the original
observations; historical measurements were not overwritten. See the
[named-results acceptance record](tasks/scenario-named-results-acceptance.md).
The original same-actor behavior above records that historical delivery. The
user/session task replaced it with a single-user child alias mapped to the
effective parent user. The separately approved mixed-user task now adds complete
maps for multi-user leaf children without permitting deeper nesting.
Historical task specifications and measured outcomes remain
records of their original engine. Current executable review-exercise YAML and
sidecar pins are explicitly migrated to `users`; that migration does not recreate
the historical measurements or imply renewed human approval.
No review-cost or real-product adoption improvement is claimed, and no private
Scenario migration or multilevel inclusion is authorized.

The bounded exercise prepared three independent changes to the same public
Demo create/update/read flow, with paired flat and included declarations. It
checks the review materials technically before asking a person to review them.
Normal execution, fault-control results, human review correctness, and human
effort remain separate observations. No private product evidence, deeper nesting,
new YAML syntax, or review UI is part of this exercise. Independent focused checks passed
45 tests; full regression passed 1146 with one existing warning and no skips.
See the [preparation acceptance](tasks/scenario-review-exercise-acceptance.md).
The [human review packet](review-exercise/README.md) remains an optional,
unmeasured comparison, not a blocker to further work. Its original cases and
technical evidence are preserved; no review answers or timings are inferred.
The accepted follow-up is a [minimal create/read reuse walkthrough](../examples/scenario-reuse/README.md)
using the approved expression and existing Demo. It explains which unchanged
child review can be reused across callers and which caller decisions still need
review. Its exact approved YAML/pin and real Demo execution passed six added
checks; independent combined verification passed 51 tests, and full regression
passed 1152 with one existing warning and no skips. No general human-effort
saving is established by that walkthrough. The 28-file delivery was submitted
through PR #17 and merged in `967af3c4f96a8b5ebbf1e12f624aa1b789698b2b`.
All eight branch/PR checks and all four post-merge main jobs passed; task branches
were removed and main synchronized. No private workspace was accessed.
Historical local acceptance retains its original pre-submission statements.

Read-only shared-child impact inspection is now delivered: explicit
old/current child inputs, a bounded caller directory, structural differences,
caller wiring and named-result use, with unknown evidence shown explicitly.
The command does not refresh pins, infer approval, change YAML or runtime
semantics, or claim review-cost savings. Independent verification passed 90
focused and adversarial checks; final full regression passed 1217 tests with
real Demo execution, no skips and one existing dependency warning. A deep-tree
inspection failure found by audit was repaired and independently rechecked.
See the [usage guide](impact-review.md) and
[acceptance record](tasks/scenario-impact-review-acceptance.md). The accepted
changes were submitted through PR #18 and merged in
`67ce17f8855f976d138ee84e34e2df5fdde31cbe`; all eight branch/PR checks and four
post-merge main jobs passed. Historical local acceptance retains its original
pre-submission statements.

Graphical Scenario authoring, deeper or dynamic Scenario composition, intent hierarchies,
cryptographic approval infrastructure, automatic approval propagation, and
general-purpose temporal or schema engines
remain deferred ideas, not queued implementation tasks. Reconsider only when a
specific use case and evidence justify the added scope.

## Delivery gates

For each task: specification and explicit authorization → development →
independent audit against that specification → architect acceptance → a
separately authorized submission. Implementation or audit success does not
authorize staging, committing, pushing, or merging. Submission must follow the
repository's working agreement and required CI; this index does not bypass it.

Record what was actually checked. Declaration validity, human approval,
execution success, and a release decision are different claims. In particular,
execution success does not prove every business obligation has sufficient
evidence, and multiple checks on the same source do not make that source
independent.

## Public information review

Public task material must be product-neutral and have an explainable source:
public code and documentation, explicitly approved neutral requirements, or
independently constructed synthetic examples. Material derived from non-public
discussions requires a fresh, scoped review and maintainer approval before
publication; replacing names alone is not sufficient sanitization. Non-public
source records and evidence remain outside this repository.

Before submission, review the complete public diff and its provenance, including
comments, configuration, CI filters, scripts, tests, examples, filenames, and
links. Review commit messages and pull-request text as well. Do not encode
private organization or product names in a public denylist or CI filter: that
filter itself would publish them. Exclude private paths, evidence, credentials,
and unapproved measurements. Repository hygiene checks are supplementary;
passing them does not prove information-source neutrality.
