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
| 1 | [Action-oriented Scenario format](tasks/scenario-action-format.md) | Core and adapter delivery independently audited and architect-accepted; workbench withdrawn. | Authorized submission with the dependent collection task, subject to CI and merge gates. |
| 2 | [Bounded response collection assertions](tasks/response-collection-assertions.md) | Implemented, independently audited, and architect-accepted. | Authorized submission, subject to CI and merge gates. |

The maintainer authorized implementation after approving the explicit do.request
and polling form, and subsequently approved the bounded collection expression.
Submission is authorized only after development, independent audit, and acceptance.
The approved expression remains its basis; implementation convenience must not
silently change its meaning.

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

Graphical Scenario authoring, Scenario composition, intent hierarchies,
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
