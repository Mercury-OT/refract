# Scenario review exercise: preparation acceptance

## Decision

Technical preparation: **PASS**, following development, independent audit, and
architect verification on 2026-10-15. Human review: **PENDING / UNMEASURED**.
This accepts the exercise materials, not a claim of lower review cost or better
approval quality. No submission is authorized or performed.

The [specification](scenario-review-exercise.md) is the task authority. The
[participant packet](../review-exercise/README.md) contains the first review pass;
its answer key is separate. Requirements are synthetic and can be challenged by
the participant before judging changes. Responses and personal effort data have
not been invented or written into this repository.

Starting and ending public HEAD: `f5d258aa68af64c7792b7e09d583292fd482788c`, equal
to local `origin/main`. All changes remain unstaged and uncommitted. Private
workspaces and products were neither accessed nor changed.

## What was delivered

One baseline and three independent changes, each with an included parent, child,
exact child fingerprint, and independently authored flat form. The pairs use the
same actions and every assertion. They are not generated from the expander.

The three changes exercise a local step rename, different caller wiring, and a
removed assertion. Technical checks confirm the proposed changes are exactly
those described, including changed/unchanged pins. First-pass excerpts exactly
match source diffs and link to complete sources. No YAML syntax, core, adapter, CI,
maintained example, MANIFESTO, or BRAND change was made.

## Observed verification

Commands ran from the public repository with its existing locked environment.

| Check | Actual result |
| --- | --- |
| `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/test_scenario_review_exercise.py tests/demo/test_demo_review_exercise.py` — developer | **45 passed**, 11.07 seconds: 29 offline checks and 16 fresh-server Demo executions. |
| Same command — independent auditor | **45 passed**, 10.94 seconds. No actionable findings. |
| `uv run --locked --no-sync python -B -m pytest -o addopts='' -q` — architect | **1146 passed**, no skips, one existing Starlette/httpx deprecation warning, 137.51 seconds. |
| Load all `docs/review-exercise/*/*.yaml` through existing `load_scenario` | All **12** sources valid; four exact sidecars verified. |
| `uv run --locked --no-sync refracto validate docs/review-exercise/baseline/included.yaml --expand` | Passed; existing explicit symbolic review view works unchanged. |
| `uv lock --check`; repository hygiene; tracked diff/cached diff checks | Passed; index empty. New untracked material was also inspected for source neutrality, local paths, and whitespace. |
| Core, adapters, existing examples/fixtures, CI, language documentation, dependency files, and historical acceptance evidence | No diff. |

Eight normal backend flows (four versions, two forms) passed without degradation.
Eight corresponding runs injected one bounded observation fault: the existing
Demo StateProbe was read over real HTTP, its creation count verified as 3, then
only that returned observation changed to 2. Six runs detected it and blocked
later actions; the two with the count assertion removed did not detect it.
The ordinary wrong-wiring run actually sent and received the changed name; its
normal execution passing does not approve the changed requirement.

This is a selected observation-fault check, not a product-storage mutation,
independent database audit, overall quality percentage, or UI/contract claim.
The tests use the existing runner `now`/`sleep` seam to advance observation waits;
HTTP, trace reads, and evaluators remain real and unchanged. No runtime benchmark
claim is made. Exploratory slow runs, including an architect run interrupted at
86 passed before the final harness rerun, were not counted as completed checks.

## Accepted preparation file scope

Exactly **23** public files; no historical files are rewritten:

- `docs/roadmap.md`: factual prior-delivery status and this exercise's next gate.
- `docs/tasks/scenario-review-exercise.md`.
- `docs/tasks/scenario-review-exercise-acceptance.md`.
- `docs/review-exercise/README.md` and `answer-key.md`.
- For each of `docs/review-exercise/baseline/`, `case-01/`, `case-02/`, `case-03/`:
  `included.yaml`, `included.includes.json`, `child.yaml`, and `flat.yaml`
  (16 files total).
- `tests/test_scenario_review_exercise.py`.
- `tests/demo/test_demo_review_exercise.py`.

Public sources are the already published Demo API/StateProbe, implemented
Scenario syntax, and the explicitly identified synthetic exercise requirements.
No private product data, adapter, evidence, local path, or personal measurement
is part of the materials. Automated hygiene is supplementary to that review.

## Remaining gate

Ask the participant to judge the first three changes and identify confusing or
costly parts. Active time is optional and self-reported, with setup and child/pin
inspection included. After the first response, offer the opposite forms while
preserving the first answers. Missing answers/times remain missing.

The second pass has learning bias, and three cases from one person cannot prove
a general or causal benefit. No new nesting, language feature, review UI, or
automatic approval propagation follows from this preparation. Do not publish
personal responses without separate permission. Human review benefit remains
unmeasured until actual feedback exists, and may remain inconclusive afterward.

## Follow-up acceptance: minimal reuse walkthrough

On 2026-10-15 the practical create/read example and review guide received
independent audit and architect acceptance: **PASS**. This follow-up supersedes
the mandatory next-gate wording in the earlier Remaining gate section. The
three-case comparison remains optional and **UNMEASURED**; it has not acquired
answers, times, an approval score, or a cost-saving result. A walkthrough
confirmation is not a substitute for that comparison. Personal feedback is not
published here.

The example preserves the approved minimal expression: the child creates and
checks one item, offers two named results, and the parent reads the collection
using the actual ID and the independently specified input name. It adds no rows,
update operation, or checks beyond the approved pair, and no new syntax or
runtime capability. Comments and the
usage guide are English. The sidecar pins the actual child bytes with SHA-256
`e13f1416cac5a6b6ea4bdebe92bf134dcddc23450d5e1fe919de15fcc758819b`.

The guide distinguishes reusable child review from caller-specific decisions,
and repeated execution from reuse of review. Multiple parents can share a stable
child, but the potential savings and change-impact costs are not quantified.

| Follow-up verification | Actual result |
| --- | --- |
| Developer: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/demo/test_demo_reuse_walkthrough.py` | **6 passed**, 1.21 seconds. |
| Independent audit: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q tests/test_scenario_review_exercise.py tests/demo/test_demo_review_exercise.py tests/demo/test_demo_reuse_walkthrough.py` | **51 passed**, 12.10 seconds; no blocking findings. |
| Architect: `uv run --locked --no-sync python -B -m pytest -o addopts='' -q` | **1152 passed**, no skips, one existing deprecation warning, 138.67 seconds. |
| Parent/child `refracto validate`; parent `--expand` | Passed; exact pin and named response sources verified. |
| Lock, repository hygiene, diff/cached diff, and new-file information-source review | Passed; index empty. |

Two fresh real Demo runs begin with an unrelated record, respectively using a
different name and the same name as the requested record. Both runs are PASSED
with no degradation. The observed created ID differs from the pre-existing ID,
the parent binds that ID, and the list has two members but only one matching the
ID/name pair. Tests also check the exact parsed declarations and two explicit
binding IDs. This is backend example verification, not human review-cost,
UI, real-product adoption, or database-independence evidence.

An exploratory audit command interleaving root-level and Demo test file paths
had 16 fixture-discovery setup errors; the grouped command above and standalone
new suite passed. A mistaken hygiene filename failed before the actual shell
check passed. These exploratory failures are not counted as passing checks and
were not suppressed by implementation changes.

The cumulative pending public scope is now **28 files**: the earlier 23 plus
`examples/scenario-reuse/README.md`, `create_read.yaml`,
`create_read.includes.json`, `shared/create_item.yaml`, and
`tests/demo/test_demo_reuse_walkthrough.py`. Within the earlier scope only the
task follow-up, this appended acceptance note, the roadmap status, and the
optional-packet notice changed for this follow-up. Original exercise YAML,
pins, answer key, and tests were not edited. Four previously recorded child
hashes still match; no complete prior hash manifest for all untracked exercise
files is claimed. Tracked core, adapters, original scenarios/examples, dependency
files, and historical include/named-results evidence have no diff.

HEAD remains `f5d258aa68af64c7792b7e09d583292fd482788c`, equal to local
`origin/main`. Private workspaces were not accessed. No staging, commit, push,
or PR was performed. A separate submission authorization is still required.
