# Execution and authoring boundary hardening

Status: implementation, independent audit and local architect acceptance passed
on 2026-10-20 under the maintainer's bounded correction authorization.
Submission still requires separate authorization. Starting main: `786b5ba`.
No staging or publication.

## Purpose and sources

Correct reproducible failures of the public declaration, execution and evidence
contracts. Sources for this specification are the public implementation, current
Scenario contract and independently constructed synthetic reproductions. No
private application, case inventory, identifiers or measurements are inputs to
the public tests or examples. Private workspaces remain untouched.

This work does not add a capability, a check, a reference form, a projection or a
new format version. Run-unique values remain paused. Passing these regressions
does not prove complete correctness or adoption value.

## Corrections

1. **Reference-capable values.** An unknown `from_` key in an authored position
   that accepts references is a declaration error, not a literal expected object.
   This includes recursive action data, assertion values and include arguments
   where references are already interpreted. Parameter dictionaries remain
   literal data; runtime observations are never parsed as declarations. This
   bounded namespace reservation was explicitly approved on 2026-10-20. It is
   not a universal spelling checker.
2. **Ambiguous YAML scalars.** Reject YAML 1.1 implicit boolean aliases,
   sexagesimal numbers and leading-zero octal spellings instead of silently
   changing their types or values. Explain quoting or explicit decimal spelling.
   Quoted strings and unambiguous existing literals retain their behavior.
   This conservative validation tightening was explicitly approved on
   2026-10-20; it is not a wholesale YAML dialect migration.
3. **Dot path segments.** Reject standalone `.` and `..` logical segments.
   Known literals, parameters and include substitutions fail declaration
   validation; response-derived unusable segments block only their consumer
   before action. Reject raw dot-segment transport paths before sending.
   Ordinary punctuation, encoded literal percent data and segment-local slash
   encoding remain data. No raw-path security-testing facility is introduced.
4. **Contract execution boundaries.** Validated backend provenance can establish
   that a declared consumer was never executed because it was blocked. Retain
   that visible nonpassing outcome instead of inventing a missing-endpoint
   assertion failure. Missing, duplicate or contradictory provenance must not
   authorize omission. A recording for supposedly unexecuted work is an error.
   Without execution provenance, missing evidence remains fail-closed.
   Selection/dependency errors belong to their consumer and must not erase
   checks on independent endpoints. Impossible dependencies of an allegedly
   executed request remain errors. The polled step's own non-final recording
   still cannot satisfy contract's final-only requirement.
5. **State evidence.** Ordered span-attribute comparisons require actual finite
   numbers, excluding booleans. Poll timeout does not query state for a non-final
   response, but each declared state check must be reported as not checked.
   Existing timeout outcomes, stopping behavior and strict pass gate stay intact.
6. **Observed query separators.** Ignore empty separator-only chunks in actual
   URL queries. Real empty-name parameters, duplicate decoded names, malformed
   encodings and unsupported evidence still fail. No expected query value may
   repair or manufacture observed data.
7. **Regression controls and example fidelity.** Add a live test requiring the
   already detected synthetic fault controls to remain detected. Preserve all
   frozen measurement inputs and historical results byte-for-byte. Couple the
   minimal example's action name to the same parameter as its expectation.
   Check the onboarding guide for copied declarations; its current example link
   needs no duplicate YAML update.

## Explicit exclusions

Do not change wait/session policy, introduce runtime branching, add cleanup
guarantees, alter contract's purpose, remove legacy Python constructors, unify
all evaluators, split large modules, delete historical evidence or change any
assertion vocabulary. No new observation channel, environment-input declaration,
request body form, UI action, unique value or relative-time facility.

## Tests and acceptance

- Reproduce incorrect behavior before each correction; test valid neighbors.
- Check nested include argument handling without interpreting literal parameter
  dictionaries as executable references.
- Exercise response-derived path rejection before API/browser action, then an
  independent step, and retain sensitive-value boundaries.
- Test blocked consumers together with later independent success/failure,
  includes, selected-member ambiguity, and absent or contradictory provenance.
  Do not relax provider identity, user/session or final-recording checks.
- Check boolean/nonfinite span values, poll FAIL/SKIP state visibility, and actual
  query strings including separator-only and genuinely malformed cases.
- Independently audit the complete diff against this scope. Run focused tests,
  full regression with actual Chromium, isolated dev-only regression, the core
  import-direction litmus, repository hygiene, lock and diff checks.
- Verify assertion vocabulary and historical stabilization artifacts unchanged.
  Report actual outcomes and unresolved limits; keep all changes unstaged.

Capability prioritization is discussed with the maintainer separately. Suggestions
are not implementation authority, and private review material is not copied into
this specification.

## Local acceptance

All commands below exited 0 on the final implementation. The full suite used
actual Chromium with no skips; dev-only installations intentionally omit the
optional Demo integration.

| Check | Observed result |
| --- | --- |
| `uv run pytest -o addopts='' -q` | 3735 passed, no skips, one existing dependency warning |
| Five new regression files with `pytest -o addopts='' -q` | 214 passed |
| Independent audit's focused regression | 711 passed |
| Fresh Python 3.11 dev-only install, `python -m pytest -o addopts='' -q` | 3259 passed, 1 optional skip |
| Fresh Python 3.12 dev-only install, same command | 3259 passed, 1 optional skip |
| `uv run pytest tests/test_stabilization_boundaries.py -o addopts='' -q` | 42 passed |
| `uv run pytest tests/test_opensource_litmus.py -q` | 3 passed |
| `uv run python scripts/measure_stabilization.py --verify` | Frozen inventory verified |
| `uv lock --check`; `bash scripts/check_repository_hygiene.sh`; Git working/staged diff checks | Passed; staging area empty |

The new files are `test_authoring_value_boundaries.py`,
`test_path_segment_boundaries.py`, `test_contract_execution_boundaries.py`,
`test_execution_evidence_edges.py` and `test_stabilization_nonregression.py`,
all under `tests/`. Fresh isolated environments were created with `uv venv
--python 3.11 <env>` (and 3.12), then `uv pip install --python
<env>/bin/python -e '.[dev]'`; their tests do not depend on the main environment.

Independent audit found one additional false-pass path: plain response references
were not checked at their use sites during contract replay. The correction now
uses the same preparation rules for plain and selected-member references. Its
independent reproduction and 24 added path/query/header controls passed, retaining
independent endpoint checks. Six actual Chromium query-separator probes and two
mock/live UI dot-reference probes also passed independent review.

During development, an interim full run still held 11 old aggregate-error test
expectations. They were explicitly changed to require visible consumer BLOCKED,
no invented endpoint mismatch and fail-closed behavior without provenance.
The final clean-process full run above supersedes that interim run.

The assertion vocabulary, lock file and eleven frozen stabilization source/result
files are byte-identical to the starting revision. Historical measurements were
not regenerated, deleted or promoted into broader correctness claims. The twenty
changed/new files contain only public-code corrections and synthetic tests;
private workspaces were not accessed. All changes remain unstaged on the original
main revision. Hosted CI, submission and real-product adoption are not claimed.

## Subsequent submission authorization

On 2026-10-20 the maintainer accepted the completed work and separately
authorized its task-branch commit, push, pull request, merge after green checks,
post-merge main CI verification and branch cleanup. The local acceptance above
remains the pre-submission record; it does not claim those later actions have
completed. Git history and the task PR provide their separate delivery evidence.
Run-unique expression review may resume after delivery, without implementation
authorization. Private workspaces remain outside this submission.
