# Stabilization: bounded evidence and review boundaries

## Gate, priority and non-goals

**Approved specification; Phase B authorized on 2026-10-18.** The maintainer
accepted this specification and its adjusted scope, requested the four groups
in order with development, independent audit and architect acceptance, and
explicitly withheld staging, submission and private-workspace changes. The
run-unique-value proposal remains paused. Phase A produced this specification;
Phase B delivers the four groups below. Submission requires separate maintainer
authorization.

Freeze new declaration work, including run-unique values, relative time,
adapter-conformance features and satellite extensions, until all four groups
are accepted. Resuming the paused proposal does not approve its YAML or its
implementation. Keep `schema_version: 1`, current YAML, vocabulary, ports,
execution semantics and one-level inclusion unchanged.

No staging, commits, pushes or private-workspace access. Do not read real-product
sources or evidence. Public material must derive only from public repository
facts and independently specified synthetic controls, with English prose and
repository-relative paths. Do not publish private terms even in scanning rules.
Do not change MANIFESTO, BRAND, dependencies, CI configuration, production
adapters or target applications. No workbench, documentation split, general
mutation engine, vocabulary removal or contract-positioning decision.

In the main checkout, **all tracked `refracto/` source files remain byte-identical
to the start**.
The two explicitly specified engine mutants below are temporary test subjects
in detached checkouts, not delivered core changes. New tests, test-only injection
wrappers, measurement tooling and bounded documentation corrections are allowed
in Phase B. A discovered implementation defect is reported and escalated, not
silently fixed under this task.

## Verified starting points

- Current main: `936c50aee490ff9d97ec7ee8bbd207f94de5eda5`.
- Before this batch: `d2a5ed9^`, resolved to
  `67ce17f8855f976d138ee84e34e2df5fdde31cbe`.
- `refracto/declaration/vocabulary.py` SHA-256:
  `254e24d8b7a6f74cde2dfead19f56178d61f7bc5f4d9468d406b5ea2b83acfb1`.
- SCENARIO.md has 1,212 lines and 15 YAML fences at the starting revision.

The ten capability groups are status assertions (`d2a5ed9`), failure continuation
(`95ba66d`), users/sessions (`b2fdab2`), rejection evidence (`eaca8cb`), query
(`68af23a`), anonymous inclusion mappings (`0c14865`), headers (`b3ddace` plus
`73b356f`), complete field comparisons (`b7996c4`), member references (`75db346`),
and numeric/list-length checks (`936c50a`). Headers include their follow-up fix;
eleven commits do not imply eleven capability groups.

Existing targeted fault tests already demonstrate bounded detection, including
`tests/test_rejection_evidence.py::test_removing_only_reason_check_demonstrates_ambiguous_403_false_positive`.
This task supplies a common inventory, repeatable comparisons and a compact
review surface; it does not claim earlier work had no strength evidence.
Mutation detection is one measure for a selected fault set, not the sole quality
measure, a product-quality percentage, evidence independence or adoption value.
The presumed reduction in maintainer effort remains unmeasured.

## 1. Backend control measurements

### Comparable historical panel

Use two detached checkouts at the exact revisions above, their revision-native
`tests/named_results_fault_controls.py`, compatible isolated Python environments
and each revision's lock file. Freeze engine, harness, declaration and injection
hashes before measurement. Run an import-origin probe from outside either source
directory; record resolved checkout revisions, interpreter and dependency versions.
Do not run current users/session declarations against the old actor loader and
count its rejection as detection.

The common panel is the three existing faults: `accepted_rejection`,
`changed_collection_target`, and `wrong_object_read`. Run each in flat and include
form, with and without injection: 12 executions per revision, 24 in total. Report
three faults per form separately; the two forms are not six distinct defects.
Preserve `tests/include_fault_controls.py` and the two original
`tests/include_fault_controls_{baseline,candidate}.json` files byte-for-byte.
New measurements must have new filenames and identify this different baseline.

Review the two harnesses' differences before comparing. Preserve target fault,
observed obligation and intended failing check; document actor/user migration
and changed continuation behavior. Compare detection and the relevant observed
prefix, while also reporting all later actions. Do not demand byte-identical
reports across an intentional execution-policy change or hide that difference.
Equal before/after detection is a valid result, not a failed experiment.

### Current-only panel

Use the existing public Documents pipeline and test-only faults. Reuse existing
tests and injection points where possible. Each row has a passing control and
one specified fault; freeze the exact fixture/check mapping and hashes before
recording scores. The following 14 rows bound this panel; do not silently add
faults, replace survivors or retune expectations after seeing results.

| ID | Group and injected difference | Required observation / measurement lane |
| --- | --- | --- |
| F01 | Status: change 201 to 202, preserving the successful body | `status_equals` fails; assertion lane |
| F02 | Continuation: wrong stored creation title causes creation and read checks to fail, then deletion succeeds | Both failures retained, all three actions observed, final FAILED; assertion plus report-integrity control |
| F03 | Sessions: revoked permission remains usable in the already-open session | Old-session refusal check fails; assertion lane |
| G01 | Users: two declared users resolve to one principal | Exact identity ERROR, no authentication/business actions; guard lane |
| F04 | Rejection evidence: retain 403 but replace ownership refusal reason with validation reason | Reason `field_equals` fails; assertion lane |
| F05 | Query: ignore the declared category filter | Declared member/content obligation fails; assertion lane |
| F06 | Anonymous inclusion: faulty target admits the anonymous reader of an owned document | Parent's exact 401 obligation fails after included execution; assertion lane |
| F07 | Headers: repeated idempotency key creates a second record while echoing the first ID | Actual effect-count obligation fails; assertion lane |
| F08 | Headers: remove the actual Location header from a successful creation | `header_equals` fails; assertion lane |
| F09 | Full comparison: a refused peer update nevertheless changes stored content | Creator's later complete-field equality fails; assertion lane |
| G02 | Member references: two actual members match the selector | Consumer BLOCKED for ambiguity, zero subsequent PATCH; guard lane |
| F10 | Numeric/length: actual page contains more members than the declared limit | `collection_length` fails; assertion lane |
| C01 | Engine mutant: restore stop-on-ordinary-FAILED behavior | Focused continuation test detects missing later action/check; engine-test lane |
| C02 | Engine mutant: later success erases an earlier failure during aggregation | Focused report test detects the incorrect aggregate; engine-test lane |

F02 and C01/C02 share a business fixture but answer different questions. C01/C02
use individually hashed minimal patches only in disposable detached checkouts;
do not mutate vocabulary, test expectations or the main checkout. The unmutated
engine must pass the same test, including its expected FAILED business report.
An import error, syntax error or unrelated exception does not kill an engine
mutant. Record the exact failing test assertion and the reached mutated branch.

For F/G controls, the unmodified neighbor must be strict PASSED with no
degradation. Fault injection must actually reach its specified boundary. G02
must not rely on a preceding count assertion to detect ambiguity. F10 checks the
actual list, not a derived reported count; the existing independent Records
false-count test remains a separate regression, not a second independent
Documents witness. Do not synthesize observations from expected values.

Freeze fixture IDs, source paths, control/injection hashes, detector test/check,
expected reach count and action count before execution. Independent audit checks
this mapping against the fixed rows. A row that cannot be faithfully constructed
is reported as blocked with a reason; replacing its meaning requires maintainer
confirmation, not a convenient alternative chosen after measurement.

### Records and interpretation

Each record identifies revision, panel, row, form, injection flag, fault layer,
projection, relevant hashes, command/exit code, import origin, control outcome,
reach count, exact check or guard result, action count and classification. Keep
raw neutral results and a reproducible command entry point. Public results
express import origins relative to the identified checkout; command recipes use
variables/relative paths, not machine-specific paths or credentials.
Unexpected nonzero commands cannot disappear from the report.

Use separate counters and denominators:

- Assertion detection: detected / (detected + missed), only valid reached
  assertion-lane faults. F02 counts once, not once per failed check.
- Guard conformance: exact expected blocking behavior versus guard misses.
- Engine-test mutation: designated test kills versus surviving mutations.
- Always show planned, executed, not-reached, invalid-control and unsupported
  rows alongside these numbers; denominator zero means N/A.

Generic ERROR, loading/setup failure or a failed clean neighbor is an invalid
control, not detection. Wrong guard reasons are not successful interception.
New-feature controls without equivalent old declarations are not a before/after
comparison: mark baseline applicability explicitly. Never combine the historical
panel and current-only panel into a claimed improvement percentage. No frontend,
UI e2e or contract detection rate may be inferred from backend results.

For valid misses, use V (unexpressible obligation), S (expressible but not
asserted), or P (not distinguishable through the permitted observations), with
evidence and uncertainty. Allow unresolved attribution. Harness failures and
violations of an existing engine promise are separate findings, never P. No
score target authorizes removing a fault or adding capabilities. Valid survivors
are acceptable evidence; invalid controls or confirmed engine defects prevent
unqualified final acceptance and require an explicit follow-up decision.

## 2. Compact negative-declaration review

Deliver `docs/boundaries.md`, grouped by top level, step, do, expect and reference.
Each short row contains a stable ID, exact YAML fragment, one rejection reason,
and a repository-relative test node reference. Use three representative cases
per capability group, sharing existing boundaries where appropriate; keep at
most 30 distinct entries on one compact reading page. This is not a literal
printed-page guarantee or a new language policy.

Rejection evidence introduced no loader syntax. Its three relevant declaration
boundaries reuse status/field shape checks; its missing/confused-reason failures
are separately linked runtime controls, not YAML that the loader must reject.
Do not invent loader restrictions to meet a quota. If an alleged boundary is
currently accepted, report the discrepancy rather than change the loader.

A sentinel must parse the actual documented fragments, insert each into a
specified minimal valid context, and require `DeclarationError`. First prove the
context without the fragment loads. Do not count generic exceptions, placeholder
ellipsis or unrelated invalid context as rejection. Verify each cited test node
exists and is collected (including a specific parameter case when necessary),
and that it exercises that boundary. Add missing tests before listing an entry.
Check exhaustive ID/context mapping: no untested rows or silently ignored rows.
Full wrapper fixtures belong in tests, not in the compact page.

## 3. Vocabulary and contract maintenance review (report only)

Inventory response-side equality paths and their domains. Include full
`field_equals`, numeric `field_compare(op: ==)`, exact list length, matching count,
status equality/set membership and header equality. For each apparent overlap,
give an equivalence domain or counterexample, affected maintained examples/tests,
and a keep/restrict/defer recommendation. Do not equate list length with matching
count, raw status/headers with normalized fields, or absence with inequality.
No syntax rejection, removal, example weakening or vocabulary change is authorized.

Inventory every tracked `status_in` use, classifying executable acceptance
declaration, shared child, documentation illustration or test-only boundary.
Record the stated multiple-status obligation and any parent strengthening.
Missing rationale is a review candidate, not invented product intent. In
particular, inspect the shared Documents `[401, 403]` child together with its
parents' exact status/reason checks; a broad child promise does not automatically
weaken those composed promises. Do not apply a new loader requirement here.

For each of the ten groups, report added/deleted lines for direct contract files
(`refracto/contract/` and `refracto/projection/contract.py`) against each commit's
parent. Include both header commits, distinguish gross churn from net diff, and
record zeros. Separately list shared reference/evaluation/identity/report changes
and supporting tests; do not double count these as direct contract lines.
Give each change's protected property, test evidence, and whether it would still
be necessary, unnecessary or undecided under a hypothetical cross-version or
cross-environment-only role. Lines are not measured engineering hours. Contract
uses backend recordings; changing its positioning does not establish independent
evidence. Present tradeoffs without deciding the future role.

## 4. Documentation consistency and narrow corrections

Inventory roadmap and task acceptance status against actual Git history. Correct
current stale index claims. Preserve dated local-acceptance statements such as
"not yet committed"; append a separate subsequent-delivery line with verified
commit/PR evidence where useful. A local acceptance, publication and hosted CI
are different claims: a merge commit alone does not prove CI success.

Map all 15 starting SCENARIO.md YAML fences exactly once to their validation
context: full Scenario, contextual declaration fragment, or other structured
artifact with its proper validator. Any added fence must enter the inventory.
Load the actual text, not a similar copy. Supply real include children/pins for
fragments that need them. Check referenced example paths exist; distinguish
loader-only coverage from real execution, identify the owning CI-collected test
and projections, and close missing execution coverage with existing synthetic
fixtures where appropriate. Historical/non-executable authoring artifacts must
be labeled as such, not claimed to run as current Scenarios.

`examples/authoring/rules.md` exists at the start. Its references to the absent
`.claude/skills/refract-authoring/SKILL.md`, and related present-tense README
claims, need narrow correction or historical labeling; do not create a new skill.
Produce a consistency list with original claim, evidence, correction and test.
No historical record rewrite, broad SCENARIO restructuring or new usage policy.

## Phase B deliverables and acceptance

1. Measurement report: `docs/tasks/stabilization-20261018-measurements.md`, with
   repository-local neutral test fixtures/patches, machine-readable results and an
   executable reproduction entry point. Report all three lanes separately.
2. `docs/boundaries.md` plus executable fragment/context/test-reference sentinel.
3. `docs/tasks/stabilization-20261018-review.md`: vocabulary/status-use inventory
   and contract maintenance review; recommendations only.
4. `docs/tasks/stabilization-20261018-consistency.md`: consistency list and narrow
   corrections, complete fence/example coverage, and local acceptance evidence.
   The final maintainer summary is at most 20 lines, naming the most vulnerable
   boundaries, what was actually measured, unresolved gaps and the next gate.

Before measurement, write one bounded manifest under test fixtures naming the
14 current rows, the 24 historical executions, source hashes and result paths.
The reproduction entry point must verify it and reject silent omissions or
duplicates. Do not create a general experiment management system. Existing
historical fault assets remain unchanged and are checked against their start
hashes. All four groups require independent review against this specification;
neither test counts nor a perfect detection fraction substitutes for that review.

Final checks, recorded with exact commands and exit codes:

- Full `uv run --extra dev --extra demo pytest` with actual Chromium and no
  browser skips; current real-browser scope is regression, not measured mutation
  coverage. Install the existing Chromium dependency if the environment needs it.
- Fresh isolated dev-only installation and pytest, matching core-only CI on
  Python 3.11 and 3.12; only the documented optional Demo collection skip is
  allowed. Record any unavailable environment as unverified, not passed.
- `uv run --extra dev pytest tests/test_opensource_litmus.py`, new sentinels and
  controls, `uv lock --check`, `bash scripts/check_repository_hygiene.sh`,
  `git diff --check`, and `git diff --cached --check`.
- Verify all tracked main-checkout core source bytes, the vocabulary SHA-256 and frozen
  historical assets against the start. Check no new core-to-adapter imports.
- Review public information sources, including untracked new files which the
  tracked-file hygiene script alone cannot cover. Stage nothing to run a check.
- Confirm only the accepted test/tool/documentation scope changed, the index is
  empty, and no submission or private-workspace operation occurred. Preserve
  evidence before safely removing only task-created detached checkouts.

Phase A ended with maintainer approval of this specification. Phase B completion
requires the four accepted groups, explicit findings disposition and architect
acceptance. Only then may the maintainer authorize submission or resume a
separate capability proposal. This specification is not that authorization.
