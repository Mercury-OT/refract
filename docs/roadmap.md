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
| 1 | [Scenario reuse walkthrough](tasks/scenario-review-exercise.md#follow-up-minimal-reuse-walkthrough) | Example and review guidance locally accepted. Review-cost comparison remains optional and unmeasured. | Separate submission authorization; no new language feature implied. |
| 2 | [Named Scenario results](tasks/scenario-named-results.md) | Delivered on main in `f5d258a`: multiple explicit result names, one-level inclusion. | Measure review friction without expanding the language. |
| 3 | [Scenario inclusion](tasks/scenario-include.md) | Delivered with named results in `f5d258a`: one level, identical actors, parent sidecar pins. | Preserve pin and caller-review boundaries. |
| 4 | [Browser adapter support](tasks/browser-adapter-support.md) | Delivered on main in `9bebfa7`. | Preserve the accepted support and evidence boundaries. |
| 5 | [Action-oriented Scenario format](tasks/scenario-action-format.md) | Delivered on main in `9900820`; workbench withdrawn. | Preserve the accepted expression and execution contract. |
| 6 | [Bounded response collection assertions](tasks/response-collection-assertions.md) | Delivered on main in `9900820`. | Preserve bounded matching and evidence semantics. |

The maintainer approved the explicit do.request and polling form, and subsequently
the bounded collection expression. Those two tasks have been delivered on main.
Browser support, inclusion, and named results have subsequently been merged.
The approved expression remains the basis of execution;
implementation convenience must not silently change its meaning.

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
saving is established by that walkthrough. All pending changes remain local,
unstaged, and unsubmitted; no private workspace was accessed.

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
