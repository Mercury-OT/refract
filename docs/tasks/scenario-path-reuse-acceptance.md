# Two-path Scenario reuse: local acceptance

Date: 2026-10-22. Independent audit and final architect acceptance: **PASS**
for this bounded task. No submission is authorized.
Specification: [two paths reusing one reviewed Scenario](scenario-path-reuse-verification.md).

## Baseline and scope

Public HEAD and local origin/main are
`14a7f88a5f293bae7d37560a9798c1c04ff23e36`. The preceding locally accepted
run-values work remains uncommitted. Its source and tests were preserved; its
test counts and implementation are not this task's deliverables. The maintainer
confirmed the new deletion parent and requested this local verification before
any separately authorized submission. No private workspace or product was read
or changed.

The existing creation child and create/update/read parent remain byte-identical.
Their baseline digests, including the existing sidecar, are guarded in
`tests/test_scenario_path_reuse.py`. Of 344 repository files captured at task start,
341 remained byte-identical; only this task's existing specification, roadmap
and reuse README changed. Newly added files are listed below.

## What was verified

- Added the approved create/delete/read parent, pinned to the same unchanged
  child as the existing update parent. No declaration, runtime or adapter
  capability was added. Both parents retain format 1 and one-level inclusion.
- Real Demo HTTP runs exercise update-then-delete and delete-then-update. Each
  ordering uses one target process and the same adapter instance. Each parent
  executes its own POST and receives a different ID within that target.
- PUT/DELETE and final list assertions use the ID from that parent's current
  creation response. An unrelated item with the deletion input's name remains
  unchanged. At the end, the updated item remains with its expected new name,
  and the deletion path's created ID is absent.
- Credentials are reused within a parent; the next parent obtains a distinct
  authentication identity and credential object for the same logical account.
  Observed request trace headers match their respective step traces. This
  checks adapter/core session handling, not real Demo server authentication.
- Existing validate/expand preserve child checks, user mapping and public
  results without executing an adapter or generating a value. Existing impact
  inspection finds both selected callers, their stale pins, and consumed-result
  breakage without writing sources or automatically renewing approval.

### Counterexamples and limits

| Control | Observed result |
| --- | --- |
| Unknown public result, undeclared user, or stale child pin | DeclarationError before adapter access; CLI validation exits 2. |
| Creation normalization omits the actually returned ID | Creation FAILED; both consumers BLOCKED; only POST is sent. |
| Update sends the initial name, while final read still requires the updated name | Create/update PASSED; final collection check FAILED. |
| List normalization omits the actually returned list | Create/delete PASSED; final zero-count check FAILED. |
| Child bytes change without repinning | Both callers found; actual declarations invalid; complete impact inspection exits 1. |
| A consumed public result is removed | Both hypothetical new callers invalid; actual stale pins remain invalid. |

The two normalization controls deliberately alter observations, not target
storage. Raw responses are checked to distinguish that fault from a product
defect. The existing review exercise still demonstrates that changing an input
and its corresponding expectation together can remain green while violating
fixed requirements. This task reuses that material, not a new approval detector.

The Demo list is complete and immediate. Zero matches do not prove absence from
a paginated or incomplete product list. The retained records demonstrate the
selected operations' behavior, not universal environment isolation. Spans are
system-reported evidence, not an independent database observer. No UI, production
adoption, cross-Scenario shared session, Flow engine or human review-cost benefit
is claimed. Human review time and quality remain unmeasured.

## Actual checks

Commands ran from the public repository root unless noted. These are local
results, not hosted CI or publication evidence.

| Check | Result |
| --- | --- |
| `uv run pytest tests/test_scenario_path_reuse.py tests/demo/test_demo_path_reuse.py -o addopts='' -q --tb=short` | Independent audit: 18 passed, 3.92 s. |
| Independent include/named-results/CLI/documentation/impact/review and HTTP regression selection | 336 passed, 25.72 s. |
| Developer new HTTP plus existing reuse/review/include tests | 38 passed, 28.70 s. |
| Root existing include/named-results/documentation/impact regression | 268 passed, 1.14 s. |
| `uv run --locked --no-sync pytest tests/test_opensource_litmus.py tests/test_scenario_path_reuse.py -o addopts='' -q --tb=short` | 15 passed, 0.23 s. |
| Fresh dev-only Python 3.11 full core suite | 3404 passed, 1 optional Demo collection skip, 40.99 s. |
| Fresh dev-only Python 3.12 full core suite | 3404 passed, 1 optional Demo collection skip, 41.84 s. |
| New 18 tests on a clean archive of committed main `14a7f88` | 18 passed, 3.88 s, including real HTTP; archive core import path verified. |
| `uv run --locked --no-sync pytest --basetemp <fresh temporary directory> -o addopts='' -q --tb=short` | Full regression: 3898 passed, no skips, actual Chromium; one existing Starlette/httpx warning, 430.47 s. |
| CLI validate for both parents | Each has 3 requests, 7 response checks and 2 state checks. |
| `uv lock --check`, repository hygiene, diff and cached-diff checks | Passed; index empty. |

The independent 336-test regression command was:

```sh
uv run --locked --no-sync python -B -m pytest \
  tests/test_scenario_include.py tests/test_scenario_named_results.py \
  tests/test_include_cli.py tests/test_include_documentation.py \
  tests/test_scenario_impact.py tests/test_scenario_review_exercise.py \
  tests/demo/test_demo_include.py tests/demo/test_demo_reuse_walkthrough.py \
  tests/demo/test_demo_review_exercise.py -o addopts='' -q --tb=short
```

The fresh core environments were installed from the locked dev-only dependencies
using the local package cache. Both were checked to lack httpx, Playwright,
Starlette and uvicorn. Their optional skip is not a substitute for the full
HTTP/browser suite.

To repeat the main-only comparison, extract `git archive 14a7f88` into a fresh
temporary directory, copy only the new deletion YAML/sidecar and the two new test
files to their corresponding locations, and run those test files from that
directory with the full-test Python environment and PYTHONPATH set to the archive.
Verify the imported `refracto` location first. This executes the committed core
without the preceding uncommitted run-values implementation.

## Independent review and final decision

Independent audit passed without implementation blockers. Its sole editorial
observation was corrected: the roadmap's planning-only restriction explicitly
applies to prospective Flow work, not this approved existing-capability task.
Development corrected two test assumptions about logical path formatting and
trace evidence location; no core behavior or approved obligation was weakened.

Final architect acceptance: **PASS**. Full regression, real HTTP and independent
audit passed; protected starting files remain unchanged outside this task's
listed scope. Existing one-level composition is sufficient for these two concrete
paths; further Flow syntax or UI implementation still needs a separately
established gap and authorization. Neither this decision nor passing tests
authorizes submission. Public HEAD and local origin/main remain at the baseline,
and the index is empty.

## Task file scope

- `docs/tasks/scenario-path-reuse-verification.md`
- `docs/tasks/scenario-path-reuse-acceptance.md`
- `docs/roadmap.md` (this task's status and bounded direction only)
- `examples/scenario-reuse/README.md`
- `examples/scenario-reuse/create_delete_read.yaml`
- `examples/scenario-reuse/create_delete_read.includes.json`
- `tests/test_scenario_path_reuse.py`
- `tests/demo/test_demo_path_reuse.py`

The roadmap also contains preceding run-values changes; those remain a separate
delivery scope. Core, vocabulary, adapters, existing Scenario sources, target
application, dependencies, CI and historical evidence were not changed by this
task. No staging, commit, push, PR, merge or private-workspace operation occurred.

## Subsequent submission authorization

After the local acceptance above, the maintainer accepted this task and assigned
a separate submission: task branch, push, pull request, green required checks,
merge, green main CI and branch cleanup. Only the eight task files listed above
are in scope. The earlier run-values implementation and documents are excluded;
their local contents remain preserved for renewed expression review. The roadmap
is curated to include this task and accurately distinguish that deferred work.
The historical local acceptance statements and combined-tree test counts above
are retained; they are not claims about this submission's main-only test count.
No private workspace operation is authorized.
