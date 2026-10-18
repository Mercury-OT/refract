# Stabilization: documentation consistency and local verification

Date: 2026-10-18. Specification: [bounded stabilization](stabilization-20261018.md).
Inspected public baseline: `936c50aee490ff9d97ec7ee8bbd207f94de5eda5`.
This fourth group adds document guards and narrow corrections, not declaration
capabilities. All four delivery groups passed independent audit and local
architect acceptance on 2026-10-18. Maintainer review and separately authorized
submission remain distinct gates. No submission is authorized.

## 1. Corrections and retained historical claims

| Original claim or question | Repository evidence | Correction or disposition | Verification |
| --- | --- | --- | --- |
| Roadmap numeric/length task is locally accepted and awaiting submission | `git log` and `git show 936c50a` contain its implementation and acceptance record in main | Mark delivered; append a separate subsequent-delivery note to its acceptance, preserving the original text/date | Git inspection below; tracked diff review |
| Users/session row says its single-user child limit "is being extended" | Main includes the completed anonymous/mapping change `0c14865` | Past-tense delivered extension | Git inspection and current loader/consumer tests |
| Mixed-user paragraph describes public submission as a future step | Same delivered change | Add subsequent main delivery, retain its pre-submission acceptance as historical | Git inspection and diff review |
| Query paragraph calls this the "current query task" | Main includes `68af23a` | Call it the delivered query task | Git inspection and diff review |
| Roadmap's next priority is another new capability | Maintainer authorized stabilization first and paused the unique-value proposal | Stabilization first; unique values, relative time, adapter-conformance features and satellites remain paused | Approved stabilization scope; no YAML approval inferred |
| Dated acceptance records say no staging/submission had occurred | Fourteen acceptance records were committed after their local verification; inventory below | Preserve every dated local claim. It is not a present index or a contradiction merely because delivery followed | Git path history; no historical dates or outcomes rewritten |
| `rules.md` points to a packaged authoring skill, and README depicts that skill as an available stage | `rules.md` exists, but `.claude/skills/refract-authoring/SKILL.md` does not | Remove the present-tense availability claim. Rules remain guidance for human or optional AI drafting, not a supplied converter | Filesystem inspection and narrow diff review |
| Authoring case files and generation log could be mistaken for executable examples | README already marks them historical drafting inputs, not current Scenarios | Preserve that explicit boundary; do not migrate or execute them as current declarations | `tests/authoring/test_case_schema.py`; README inspection |
| All contract examples are assumed loadable | The old general sentinel selected only two whole Scenarios; specialized tests covered other fragments but did not exhaustively inventory the document | New sentinel inventories all 15 actual fences, each with its stated context | `tests/test_stabilization_documentation.py` |
| A linked example could be mistaken for execution evidence merely because it loads | Exact-file consumer inventory includes `tests/demo/`, not just top-level tests | Register existing consumers and CI reachability; no duplicate consumer added | Example table and full-suite verification below |
| Minimal create/delete parameterization is reusable without qualification | Request body has literal `sample-item`; expected name refers to `parameters.item_name` | Record the fixed-input limitation below; no YAML change in this sprint | Exact source inspection; existing default-input runtime test |

### Historical acceptance inventory

All paths below are in `docs/tasks/`. These are local-verification records,
not evidence that the later hosted checks succeeded. Git establishes that the
listed changes exist in current main; it does not establish approval, CI success,
branch cleanup or production adoption. Existing historical CI claims are not
re-certified by this sprint.

| Acceptance record | Historical statement preserved | Subsequent main change |
| --- | --- | --- |
| `scenario-include-acceptance.md` | 2026-10-14, unstaged/uncommitted, local acceptance only | `f5d258a`, shared with named results |
| `scenario-named-results-acceptance.md` | 2026-10-15, local acceptance and no hosted delivery | `f5d258a` |
| `scenario-review-exercise-acceptance.md` | 2026-10-15 preparation, later walkthrough, human review cost unmeasured | `967af3c` |
| `scenario-impact-review-acceptance.md` | 2026-10-16, local acceptance, changes not yet submitted | `67ce17f` |
| `http-status-assertions-acceptance.md` | 2026-10-17, candidate YAML and submission gates pending at that point | `d2a5ed9` |
| `assertion-failure-continuation-acceptance.md` | 2026-10-17, local acceptance, no submission yet | `95ba66d` |
| `scenario-users-sessions-acceptance.md` | 2026-10-17, submission not authorized by that local record | `b2fdab2` |
| `response-rejection-evidence-acceptance.md` | 2026-10-17, local acceptance distinct from later hosted completion | `eaca8cb` |
| `request-query-parameters-acceptance.md` | 2026-10-17, local verification and isolated checks | `68af23a` |
| `anonymous-users-inclusion-acceptance.md` | 2026-10-17, unstaged files and no submission at local acceptance | `0c14865` |
| `business-http-headers-acceptance.md` | 2026-10-17 local record plus follow-up correction, not hosted success | `b3ddace`, then `73b356f` |
| `response-field-comparison-acceptance.md` | 2026-10-18, local acceptance before the separate delivery | `b7996c4` |
| `response-member-references-acceptance.md` | 2026-10-18, subsequent CI and cleanup still separate gates | `75db346` |
| `response-numeric-length-checks-acceptance.md` | 2026-10-18, local acceptance before submission | `936c50a`; separate subsequent-delivery note appended |

The recorded inspection commands were run successfully from the repository root:

```sh
git log --format='%h %ad %s' --date=short -20
git log --format='%h %s' --name-only -- docs/tasks/*acceptance.md
git show --format=fuller --no-patch 936c50a
```

These commands are review recipes, not CI requirements. The new tests require
neither a full Git history nor historical objects in a shallow CI checkout.

## 2. Every current-contract YAML fence

`SCENARIO.md` stays unchanged at 1,212 lines. Its 15 starting fences are all YAML
declarations or contextual declaration fragments; none is an unvalidated
pseudocode exception. Line numbers identify the frozen starting document, while
the sentinel uses fragment identities rather than mutable line numbers.

| Context ID | Starting line | Exact fragment | Surrounding context supplied by the test |
| --- | ---: | --- | --- |
| `query` | 199 | `next_page` step | `category` parameter and prior request-bearing `first_page` |
| `headers` | 267 | `submit` step | `idempotency_key` and `record_name` parameters |
| `comparison` | 395 | Equality/inequality check list | Prior `read_before`, `attempted_content`, current response block |
| `numeric_length` | 439 | Numeric and length bounds | `page_size`, current response block |
| `status_equals` | 517 | Exact HTTP status check | Current request-bearing response block |
| `status_in` | 522 | Alternative HTTP status check | A separate current request-bearing response block |
| `collection` | 567 | `read_list` step | Prior `create` and `record_name` parameter |
| `dictionary` | 658 | Literal key reference | Prior `create`, subsequent request body value |
| `member` | 672 | Unique-member reference | Prior `locate`, `record_code`, subsequent request body value |
| `include` | 736 | `setup` include | Single-user parent, `record_name`, real temporary matching child and raw-byte pin |
| `mapped_include` | 764 | `access` include with user map | Creator/anonymous parent, exact maintained `shared/access_document.yaml` bytes and pin |
| `results` | 793 | Child result aliases | Local request-bearing `create_request` with an actual response assertion |
| `poll` | 924 | `demo.export_ready` | Whole Scenario; no wrapper |
| `stop` | 963 | Explicit-stop step | Prior request-bearing `create` |
| `ui` | 1155 | `demo.record_create` | Whole Scenario; no wrapper |

The test reads the actual fenced bytes and adds only the stated surrounding
context. It does not parse and reserialize fragments before loading: duplicate
keys must not disappear. Real temporary files and sidecars enter the ordinary
loader. A valid neighbor is checked before each deliberately invalid fragment.
This is declaration validation, not execution or maintainer approval.

Negative controls detect missing, duplicate, newly added, unknown and unclosed
fences; malformed values/references/results; duplicate YAML keys; and changed
included bytes. Indented fences, longer markers, tilde fences, YAML/YML spelling
and extra Markdown info-string attributes cannot silently evade inventory.
All additions require an explicit context. The existing specialized tests remain
unchanged and retain their narrower runtime/reference checks.

## 3. Linked examples: existence is not execution

All **18 YAML links and two pin-file links** in `SCENARIO.md` exist. Each YAML
loads, and every one has an existing actual consumer. Child files run through
their pinned parents; the sentinel verifies the exact target file and hash.
There was no uncovered linked example requiring a new consumer.

The table names collected pytest functions; parameterization covers the listed
variants. API e2e is not browser execution. Only the explicitly labeled UI row
establishes real Chromium example execution. Contract reuses backend recordings;
its appearance is not another independent observer.

| Exact linked YAML path | Existing execution owner (`tests/` relative) | Executed projections / transport |
| --- | --- | --- |
| `examples/documents/scenarios/owner_peer.yaml` | `test_documents_users_sessions.py::test_owner_reads_and_distinct_same_role_peer_is_denied` | backend, contract, API e2e |
| `examples/documents/scenarios/permission_sessions.yaml` | `test_documents_users_sessions.py::test_permission_change_old_session_then_reauthenticate_same_account` | backend, contract, API e2e |
| `examples/documents/scenarios/shared/create_document.yaml` | Same owner/peer test, exact child included by `owner_peer.yaml` | backend, contract, API e2e; indirect |
| `examples/documents/scenarios/mapped_peer_access.yaml` | `test_anonymous_documents.py::test_same_pinned_child_maps_each_leaf_to_actual_named_or_anonymous_participant` | backend, contract, API e2e |
| `examples/documents/scenarios/mapped_anonymous_access.yaml` | Same parameterized anonymous/peer owner | backend, contract, API e2e |
| `examples/documents/scenarios/shared/access_document.yaml` | Same owner, exact child of the two mapped parents | backend, contract, API e2e; indirect |
| `examples/documents/scenarios/filter_and_next_page.yaml` | `test_query_documents.py::test_approved_five_step_example_follows_observed_cursor` | backend, contract, API e2e |
| `examples/minimal/idempotent_create.yaml` | `demo/test_demo_headers.py::test_approved_records_retry_example_uses_real_http_and_independent_target_capture` | backend, contract, API e2e; real HTTP |
| `examples/minimal/rejected_update_preserves_content.yaml` | `test_field_comparison_consumers.py::test_complete_read_before_and_after_real_refusal` | backend, contract, API e2e |
| `examples/documents/scenarios/rejected_update_preserves_content.yaml` | Same parameterized Records/Documents owner | backend, contract, API e2e |
| `examples/documents/scenarios/check_page_limits.yaml` | `test_numeric_check_consumers.py::test_real_isolated_consumers_follow_two_pages_without_mutating_evidence` | backend, contract, API e2e |
| `examples/minimal/check_page_limits.yaml` | Same parameterized Documents/Records owner | backend, contract, API e2e |
| `examples/documents/scenarios/http_status_create_delete.yaml` | `test_http_status_consumers.py::test_documents_complete_example_creates_201_and_deletes_empty_204` | backend, contract |
| `examples/minimal/create_locate_update_read.yaml` | `test_member_reference_consumers.py::test_independent_consumers_use_real_selected_identifier` | backend, contract, API e2e |
| `examples/minimal/dictionary_record_reference.yaml` | Same parameterized list/dictionary owner | backend, contract, API e2e |
| `scenarios/demo_include_items.yaml` | `demo/test_demo_include.py::test_api_include_reuses_actual_response_and_matches_flat_runtime` | backend, contract; real HTTP |
| `scenarios/demo_include_items_ui.yaml` | `demo/test_demo_include.py::test_ui_include_reuses_one_context_and_matches_flat_runtime` | frontend, live UI e2e; Chromium |
| `examples/documents/scenarios/continue_after_failure.yaml` | `test_documents_failure_continuation.py::test_documents_collect_checks_and_really_delete` | backend, contract, API e2e; clean and fault cases |

The two directly linked pin files are `scenarios/demo_include_items.includes.json`
and `scenarios/demo_include_items_ui.includes.json`. Their child hashes are also
guarded by `tests/test_include_documentation.py`. Other child relationships in the
table have their own existing sidecars and runtime consumers.

The idempotent Records declaration was already executed by its exact file path
over real HTTP, with the independent target's stored records and captured
requests. Its duplicate-effect counterexample is
`demo/test_demo_headers.py::test_records_read_detects_duplicate_creation_despite_reused_response_id`.
No new consumer or substitute declaration is necessary.

The new inventory checks source-function existence, selected node collection,
exact links, current loading and pins. Its collection subprocess includes Demo
owners when their optional dependencies exist. In a dev-only environment it
checks those owners' source definitions but does not claim to collect or execute
them. `.github/workflows/ci.yml` already installs `[dev,demo]` and Chromium in
`full-suite`, then runs all `tests/` with `pytest -q`, without a selection filter.
The final full-suite result below is the actual local execution check; source
existence and collection alone are not equivalent to that result. CI is unchanged.

The link sentinel covers the current direct inline paths ending in `.yaml` or
`.json`; it is not a general Markdown link parser. Adding fragment anchors or
reference-style links requires updating both discovery and the consumer inventory.
This limitation does not omit any of the 20 existing example links checked here.

## 4. Remaining precise limitation

`examples/minimal/scenarios/create_and_delete.yaml` sends literal
`body.name: sample-item`, while its equality check reads `parameters.item_name`,
whose default is also `sample-item`. Its default-input backend/contract and API
e2e tests pass. Changing only the parameter changes the expected value but not
the sent name. It must not be advertised as a correctly parameterized recipe.

This is a specific example-maintenance candidate, not a core expression defect
or evidence that its default run is false. Fixing its action/reference wiring
requires a separately reviewed YAML change; this sprint deliberately leaves it
unchanged. The owning default-input test is
`tests/test_minimal_onboarding.py::test_minimal_backend_and_contract_run_passes_strict_gate`.
Human review-cost savings and real-product maintenance value also remain
unmeasured; no document guard or selected mutation score closes those questions.

## 5. Verification and final acceptance

Commands run from the public repository root. Focused checks use `--no-sync` or
the selected interpreter directly so they do not alter the shared full-suite
environment. Results below distinguish completed checks from remaining gates.

The dev-only checks use two fresh environments with only the editable `dev`
extra, matching the dependency scope of the core-only CI jobs. Reproduction
recipe (the temporary directory name is not evidence identity):

```sh
VERIFY=$(mktemp -d)
uv venv --python 3.11 "$VERIFY/py311"
uv venv --python 3.12 "$VERIFY/py312"
uv pip install --python "$VERIFY/py311/bin/python" -e '.[dev]'
uv pip install --python "$VERIFY/py312/bin/python" -e '.[dev]'
PY311="$VERIFY/py311/bin/python"
PY312="$VERIFY/py312/bin/python"
```

The actual interpreters were Python 3.11.15 and 3.12.13, with PyYAML 6.0.3 and
pytest 9.1.1. The full-suite environment also had Playwright 1.62.0 and its
existing Chromium installation. No test environment or dependency was obtained
from a private workspace. The final R2 reruns below follow the one added
archive-preservation test; they therefore have one more test than the preceding
regression, not a newly introduced assertion or fault row.

| Gate | Actual result / status |
| --- | --- |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q tests/test_stabilization_documentation.py --tb=short` | 38 passed, 0.50 s; exit 0. The first 36-test pass preceded the two extra-info-string fence controls requested by independent review. |
| Preliminary full-suite attempt before the extra-info-string correction | Deliberately interrupted after 54 passing tests; exit 130. Not counted as a completed gate. The restarted final run includes all 38 documentation controls. |
| Completed regression before the measurement-harness representation correction | 3520 passed, no skips, one existing dependency warning, 411.29 s; exit 0. A subsequent untracked-file hygiene check found a source-code literal that matched the existing Windows-path rule. This is not a private path, but requires an equivalent literal rewrite and a new measurement freeze; original results remain unchanged. Final verification below must use that revision. |
| `uv run --extra dev --extra demo pytest -o addopts='' -q`, including listed HTTP/Chromium consumers | Final R2: 3521 passed, no skips, one existing Starlette/httpx dependency warning, 413.29 s; exit 0. Real Chromium consumers executed. |
| Fresh Python 3.11.15 dev-only: `$PY311 -m pytest -o addopts='' -q -rs`; separate litmus | Final R2: 3045 passed, one optional Demo collection skip for missing httpx, 39.55 s; exit 0. Litmus: 3 passed, exit 0. Not browser evidence. |
| Fresh Python 3.12.13 dev-only: `$PY312 -m pytest -o addopts='' -q -rs`; separate litmus | Final R2: 3045 passed, one optional Demo collection skip for missing httpx, 38.67 s; exit 0. Litmus: 3 passed, exit 0. Not browser evidence. |
| `$PY311 -m pytest tests/test_opensource_litmus.py -o addopts='' -q` and `$PY312 -m pytest tests/test_opensource_litmus.py -o addopts='' -q` | 3 passed in each isolated interpreter; both exit 0 |
| `.venv/bin/python -m pytest tests/test_opensource_litmus.py tests/test_stabilization_measurements.py tests/test_stabilization_boundaries.py tests/test_stabilization_documentation.py -o addopts='' -q` | Final R2: 105 passed, 1.21 s; exit 0 |
| `.venv/bin/python scripts/measure_stabilization.py --verify` | 24 historical execution identities and 14 current rows verified; exit 0 |
| `uv lock --check` | Passed; exit 0 |
| Repository hygiene, diff/cached diff, core/vocabulary/YAML freeze checks | Passed; exit 0. Read-only byte comparison confirms 115 protected files, including all 36 tracked core files, unchanged. Supplementary checks include all 18 untracked additions and four modified files; the tracked-only hygiene script is not treated as coverage of new files. |
| Independent fourth-group and complete-sprint audit | PASS, no unresolved blocking findings. Final result/status, all 22 delivery files, source freeze and original/R2 evidence hashes were independently checked. The auditor also reran the litmus and three new test suites: 105 passed, 1.50 s; exit 0. The full-suite result above is the architect's completed run, not a claimed second auditor full run. |
| Architect acceptance of all four groups | PASS on 2026-10-18 for this bounded local delivery. Selected backend evidence, boundary guards, report-only maintenance review and narrow documentation corrections meet the approved specification. The limitations below remain explicit; no new capability or submission is authorized. |

Only this group's new test/documentation files and the narrow corrections above
are changed by group four. Existing SCENARIO text, YAML, core, production adapters,
target applications, dependencies, CI, MANIFESTO and BRAND remain outside its
write scope. Public sources and synthetic examples are the only information
sources; no private workspace or product was accessed. Submission requires a
separate maintainer instruction after final acceptance.

The four groups were independently reviewed in order. Review closed two
documentation-guard gaps: compact table rows could evade the negative inventory,
and a YAML fence with extra info-string attributes could evade the fence
inventory. Direct counterexamples now fail the guards, with passing ordinary
neighbors. These are test-harness corrections, not newly rejected Scenarios.
The measurement-tool source-literal correction and fresh R2 evidence are
documented separately in the [measurement report](stabilization-20261018-measurements.md).

### Locally accepted delivery file scope

Four modified tracked files:

- `docs/roadmap.md`
- `docs/tasks/response-numeric-length-checks-acceptance.md` (append-only delivery note)
- `examples/authoring/README.md`
- `examples/authoring/rules.md`

Eighteen new files:

- `docs/boundaries.md`
- `docs/tasks/stabilization-20261018.md`
- `docs/tasks/stabilization-20261018-measurements.md`
- `docs/tasks/stabilization-20261018-review.md`
- `docs/tasks/stabilization-20261018-consistency.md`
- `scripts/measure_stabilization.py`
- `tests/stabilization_controls.py`
- `tests/test_stabilization_measurements.py`
- `tests/test_stabilization_boundaries.py`
- `tests/test_stabilization_documentation.py`
- `tests/fixtures/stabilization/C01.patch`
- `tests/fixtures/stabilization/C02.patch`
- `tests/fixtures/stabilization/manifest.json`
- `tests/fixtures/stabilization/results.json`
- `tests/fixtures/stabilization/audit-results.json`
- `tests/fixtures/stabilization/manifest-r2.json`
- `tests/fixtures/stabilization/results-r2.json`
- `tests/fixtures/stabilization/audit-results-r2.json`

These are locally accepted files, not a staged or published delivery. Main and
local origin/main remain at the inspected starting commit; the index is empty.
All task-created detached subjects have been safely removed after evidence
preservation; only the main worktree remains.

## Maintainer summary (12 lines)

1. The shared historical panel detects the same three faults before and after; it shows no detection-rate increase.
2. Current-only backend controls detect ten assertion faults, meet two guards and kill two designated engine mutations.
3. Those results cover the frozen controls, not general quality, independent evidence or other projections.
4. Failure continuation is vulnerable to later code erasing earlier failures or accidentally restoring global stop.
5. User/include boundaries are vulnerable to alias collisions, session reuse and caller mappings weakening child intent.
6. Reference boundaries are vulnerable to missing/ambiguous values becoming defaults or unchecked first members.
7. Raw status/header checks must remain separate from normalized fields and preserve actual evidence.
8. Shared contract recordings protect additional promises but do not create another independent observer.
9. Twenty-seven compact negative rows and all fifteen current-contract YAML fragments now have explicit tests.
10. All linked examples already have runtime consumers; the minimal create/delete parameter mismatch remains an explicit candidate.
11. No vocabulary, declaration shape, existing YAML, core or production adapter is changed by this sprint.
12. Final maintainer acceptance is still required; submission needs separate authorization, and the unique-value proposal remains paused.

## Subsequent maintainer decision — 2026-10-18

The maintainer accepted the complete local delivery and separately authorized
the public task branch, commit, push, pull request, required checks, merge,
post-merge main checks and branch cleanup. The earlier no-submission statements
describe the local-acceptance snapshot and remain unchanged. At this additional
authorization point, the hosted workflow has not yet completed; its actual
results must come from the task PR and CI, not this permission record.

After that workflow, the run-unique-value proposal returns to expression review
only: present a commented YAML example for confirmation, without implementation.
Relative time, adapter-conformance features and satellites remain deferred.
No private-workspace operation is authorized.
