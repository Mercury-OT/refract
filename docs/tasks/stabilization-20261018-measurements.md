# Stabilization: bounded backend measurements

The original evidence below is retained unchanged. The entry point now uses the
separate **R2 publication-hygiene freeze** described at the end of this report;
its additional execution does not add faults or change the original scores.

## Result and limits

The first recorded experiment executed all **52 planned invocations** against
the frozen subjects. There were **no invalid controls, unreached faults, skipped
invocations or unsupported rows**. These are synthetic backend measurements,
not frontend, e2e, contract, real-product adoption or independent-evidence claims.

| Panel / lane | Planned fault rows | Executed | Detected or conformant | Missed / survived | Invalid / not reached |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline common panel, flat | 3 | 3 | 3 / 3 | 0 | 0 / 0 |
| Current common panel, flat | 3 | 3 | 3 / 3 | 0 | 0 / 0 |
| Baseline common panel, include | 3 | 3 | 3 / 3 | 0 | 0 / 0 |
| Current common panel, include | 3 | 3 | 3 / 3 | 0 | 0 / 0 |
| Current Documents, assertion lane | 10 | 10 | 10 / 10 | 0 | 0 / 0 |
| Current Documents, guard lane | 2 | 2 | 2 / 2 | 0 | 0 / 0 |
| Current engine-test lane | 2 | 2 | 2 / 2 | 0 | 0 / 0 |

The common panel contains **three defects**, exercised in two forms, not six
independent defects. Each injected invocation has its own clean neighbor:
24 common-panel invocations, 24 current F/G invocations and four engine-test
invocations. The engine's two unmutated controls intentionally have FAILED
business reports; their designated test assertions pass. All 24 ordinary clean
neighbors are strict PASSED, with exact expected actions and no degradation.

**The comparable detection result is unchanged.** This does not prove the new
capabilities made those three checks stronger. The ten current-only fault rows
exercise newly available promises and are not compared with an old loader that
cannot express them. Combining the panels into an improvement percentage would
be misleading. There is no minimum detection-score gate.

## Frozen inputs and first-run evidence

- Baseline: `67ce17f8855f976d138ee84e34e2df5fdde31cbe` (`d2a5ed9^`).
- Current: `936c50aee490ff9d97ec7ee8bbd207f94de5eda5`.
- Manifest: [manifest.json](../../tests/fixtures/stabilization/manifest.json),
  SHA-256 `d8c5a3c69432a22ba0b39175b472edec17577c130bf6854f37d5f773b82da55f`.
- First results: [results.json](../../tests/fixtures/stabilization/results.json),
  SHA-256 `9f580d408298d311a71c081cb54c1caf47e5ca9d0fbe2ae509983df457fbf5bc`.
- Independent reproduction: [audit-results.json](../../tests/fixtures/stabilization/audit-results.json),
  byte-identical to the first result, with the same SHA-256. The independent
  auditor reran all 52 invocations and the 41 focused tests successfully.
- Entry point: [measure_stabilization.py](../../scripts/measure_stabilization.py).
- Current fixture/injection/detector source:
  [stabilization_controls.py](../../tests/stabilization_controls.py).
- Mechanical checks: [test_stabilization_measurements.py](../../tests/test_stabilization_measurements.py).

The manifest records all 24 historical execution identities, all 14 current
rows, exact neighbor status/step/action/reach expectations, declaration hashes,
patch hashes, both subjects' source/lock hashes, embedded historical declaration
hashes and immutable historical assets. It was independently reviewed and
released before any Scenario/control execution. Preliminary manifest hashes
`3e849153...`, `8b44c74...`, `5e24c9b...` and `41acd4d...` were superseded during
pre-measurement checks, not after observing outcomes. Changes strengthened
experiment validation, exact mutation checking and honest classification;
no fault or obligation was replaced.

The first run used four detached checkouts, each with its own locked dev-only
environment: **Python 3.12.13, PyYAML 6.0.3 and pytest 9.1.1**. Every worker ran
outside the source checkout with isolated Python startup, verified its exact
revision, and reported import origin `refracto/__init__.py` relative to that
subject. No environment from a private workspace was used.

Raw records retain all actions, normalized non-credential observations, exact
failed checks, blocked-step reasons, counts, command exit codes and engine
branch witnesses. Credentials and arbitrary report representations are not
serialized. All new evidence derives from public synthetic targets.

## Comparable historical panel

Both revision-native `tests/named_results_fault_controls.py` harnesses reuse the
same frozen target/injections and normalizer in `tests/include_fault_controls.py`.
The current declaration migrates `actor` to `users`, uses the current UserSession
interface and independently spells out the same flat obligations. Included
named-result boundaries remain equivalent. The three original historical asset
files were not edited.

| Fault | Exact detector | Baseline flat / include | Current flat / include | Injected actions: baseline → current |
| --- | --- | --- | --- | --- |
| `accepted_rejection` | `reject`: `failure` | detected / detected | detected / detected | 1 → 2 |
| `changed_collection_target` | `list`: `collection_matching_count` | detected / detected | detected / detected | 2 → 3 |
| `wrong_object_read` | `read`: `field_equals` | detected / detected | detected / detected | 2 → 3 |

Each injected fault reached once. The baseline marks the last `after` step
BLOCKED; current executes it and obtains PASSED, retaining the earlier failure
and final FAILED result. For all six injected form/fault pairs, the old actual
request and observed-response lists equal the prefix of the current lists.
The later current action is retained in the raw evidence, not discarded to
manufacture byte-identical reports. Clean controls execute the same two or
three actions on both subjects.

## Current-only row results

All rows use the public Documents backend pipeline. The fault is at the target
boundary unless otherwise stated. F08 is a test-only synthetic baseline
extension: it adds Location using the actual generated identifier. Its fresh
target deterministically creates `document-1`; the mutant removes only the
emitted Location header. Production target/adapter code is unchanged.

| Row | Observed fault and exact detector | Reach | Actions: clean / fault | Result |
| --- | --- | ---: | ---: | --- |
| F01 | Actual 201 changed to 202; `create/status_equals` fails with successful body retained | 1 | 3 / 3 | detected |
| F02 | Wrong stored title; `create/field_equals` and `read/collection_matching_count` fail; deletion succeeds, both failures remain | 1 | 3 / 3 | detected once |
| F03 | Revoked permission still usable in old session; `old_session/status_equals` and `failure` fail; new session refuses | 1 | 6 / 6 | detected |
| G01 | Authenticator maps two users to one principal; exact distinct-account ERROR, no authentication/business action | 2 identity calls | 5 / 0 | guard conformant |
| F04 | Actual 403 retains validation rather than ownership reason; `peer_reads/field_equals` fails | 1 | 4 / 4 | detected |
| F05 | Service ignores category filter; next-page member and terminal-cursor checks fail | 2 query changes | 5 / 5 | detected |
| F06 | Target admits anonymous included reader and parent reader; parent's exact 401 plus child refusal obligations fail | 2 | 5 / 5 | detected |
| F07 | Retry creates a second stored record but echoes first ID; title effect-count assertion fails | 1 | 3 / 3 | detected |
| F08 | Actual Location header removed; `create/header_equals` fails | 1 | 1 / 1 | detected |
| F09 | Refused update changes stored content; `read_after/field_equals` and `field_not_equals` fail | 1 | 4 / 4 | detected |
| G02 | Two actual members match; unique-selection dependency blocks update/read, no PATCH | 1 | 5 / 3 | guard conformant |
| F10 | Actual page contains two members despite declared limit one; `collection_length` and count/cursor checks fail | 1 | 5 / 4 | detected |
| C01 | Detached engine restores stop-on-FAILED; designated continuation test detects absent later read/delete | 1 mutated branch | 3 / 1 | killed by test |
| C02 | Detached aggregate returns PASSED after last success; designated report test detects erased failure | 1 mutated branch | 3 / 3 | killed by test |

F05/F10 raw records include the real query before and after modification and
the count of actual returned members. G02's declaration removes the earlier
count check and stop policy, so the unique-selection guard—not a previous
assertion—causes BLOCKED. G01's expected ERROR and G02's expected BLOCKED are not
counted as ordinary assertion detections. F10 demonstrates actual list length;
the separate Records false-count regression is not another Documents witness.

### Engine subjects

- [C01.patch](../../tests/fixtures/stabilization/C01.patch): only
  `refracto/projection/continuation.py`, resulting source SHA-256
  `6d263f995f095ef3edf4cd39744b40b31ed8f8e750f589a1e83a7282d903290b`.
  Executed `FlowState.finish` mutated stopper line 38; designated assertion:
  `C01: later read and delete must execute`.
- [C02.patch](../../tests/fixtures/stabilization/C02.patch): only
  `refracto/report.py`, resulting source SHA-256
  `06424076dfbed073fe12f4bb6376f2c262a56fcec2c1910d038a261e8d9c53c7`.
  Executed `DomainResult.status` inserted return line 99; designated assertion:
  `C02: later success must not erase earlier failure`.

The reproduction verifies exact patched bytes against the frozen baseline, not
merely that a patch can be reverse-applied. The two mutant worker exits **1** are
intentional failing-test evidence. Their unmutated controls exit **0**. Syntax,
import or unrelated test failure is not a killed mutant. No main-checkout core
file was mutated.

## Commands and exit codes

The following is the actual command recipe with checkout roots represented by
variables instead of host paths. `SOURCE` is the public checkout containing
these uncommitted experiment files; `SUBJECTS` is a fresh task temporary directory.
The application worktree helper could not resolve the parent checkout; exact-SHA
detached Git worktrees were used instead. That setup fallback did not run a
measurement or change the subjects.

```sh
SUBJECTS=$(mktemp -d)
git -C "$SOURCE" worktree add --detach "$SUBJECTS/baseline" 67ce17f8855f976d138ee84e34e2df5fdde31cbe
git -C "$SOURCE" worktree add --detach "$SUBJECTS/current" 936c50aee490ff9d97ec7ee8bbd207f94de5eda5
git -C "$SOURCE" worktree add --detach "$SUBJECTS/C01" 936c50aee490ff9d97ec7ee8bbd207f94de5eda5
git -C "$SOURCE" worktree add --detach "$SUBJECTS/C02" 936c50aee490ff9d97ec7ee8bbd207f94de5eda5
for subject in baseline current C01 C02; do
  uv sync --locked --extra dev --python 3.12 --project "$SUBJECTS/$subject"
done
git -C "$SUBJECTS/C01" apply "$SOURCE/tests/fixtures/stabilization/C01.patch"
git -C "$SUBJECTS/C02" apply "$SOURCE/tests/fixtures/stabilization/C02.patch"
cd "$SOURCE"
uv run --extra dev python scripts/measure_stabilization.py --verify
uv run --extra dev python scripts/measure_stabilization.py \
  --baseline "$SUBJECTS/baseline" --current "$SUBJECTS/current" \
  --c01 "$SUBJECTS/C01" --c02 "$SUBJECTS/C02" \
  --output "$SUBJECTS/reproduction.json"
uv run --extra dev pytest tests/test_stabilization_measurements.py tests/test_include_fault_controls.py
```

All four worktree-add commands, all four locked installations, both patch
applications, manifest verification, the measurement entry point and focused
pytest exited **0**. Focused pytest: **41 passed**. Before release, six
non-Scenario/static preflight tests passed; no score was collected then. The
first execution omitted `--output` and created the frozen `results.json`; the
recipe deliberately gives reproductions a new output path. Existing evidence
cannot be silently overwritten. Every one of the 52 worker commands and exits
is present in the results; only C01/C02 mutant workers exited 1 as specified.
Independent reproduction used the same four checked subjects and entry point,
with `--output tests/fixtures/stabilization/audit-results.json`; it exited 0.
Its focused pytest command also exited 0 with 41 passed. No obligation, control
code, patch or manifest changed between the first and independent runs.

The result sentinel checks the exact planned identities, manifest hash,
recomputed classifications and counters. Generic execution errors or unexpected
worker exits are invalid controls, even if other output appears to detect a
fault. Ordinary assertion survivors are allowed and reported honestly; guards
and the engine's existing execution promises remain regression obligations.

## Findings and remaining gaps

- No valid misses occurred in this selected set, so V/S/P attribution is **not
  applicable to these rows**. There is no unmeasured claim that all meaningful
  faults are expressible, observable or asserted. An unresolved miss would stay
  unresolved rather than being forced into V, S or P.
- The unchanged common score does not establish improved strength. The current
  panel adds evidence for specific newer promises, not a general quality rate.
- Neither the two guard controls nor two engine mutants measure target-product
  assertion strength. They remain separate counters.
- F02 demonstrates continued collection and retained failure, not guaranteed
  cleanup after every possible error. F03 distinguishes this synthetic target's
  live-permission policy from its session-cached policy; it is not a universal
  authentication policy.
- Documents controls use deterministic isolated state, no actual browser or
  external deployment. Browser/e2e/contract mutation coverage, private-product
  behavior, adversarial evidence forgery and maintainer review cost remain
  unmeasured by this deliverable.

Deliverable 1 passed independent review and architect acceptance; that is not
permission to submit or acceptance of the remaining deliverables. After the
independent byte-identical reproduction, the four exact temporary subjects were
rechecked. Only C01/C02 contained their specified patches; those patches were
reverse-applied and the clean detached worktrees removed without force. All
four removal commands exited 0. No other worktree was removed. The first and
independent result hashes remained unchanged; manifests, patches and the full
reproduction recipe remain available in this repository.

## R2 publication-hygiene correction and repeated measurement

The final inspection of untracked additions found that a Python bytes literal
in the measurement tool matched the existing machine-path hygiene rule. It was
source text for a newline following an uppercase identifier and colon, not an
actual machine path or secret. The rule was not relaxed or exempted. Adjacent
bytes literals now express exactly the same C02 mutant bytes without that
textual match.

This is a new measurement-source freeze, not a silent edit of old evidence.
The three original files `manifest.json`, `results.json` and `audit-results.json`
remain at their original paths and SHA-256 values listed above. A new guard
verifies all three hashes. The current entry point and result sentinel use
separate R2 paths; `manifest_version` and `result_version` remain 1 because the
experiment formats did not change. No Scenario schema or YAML changed.

| R2 artifact | SHA-256 |
| --- | --- |
| [manifest-r2.json](../../tests/fixtures/stabilization/manifest-r2.json) | `03adc4e38dbe30c59a590fdc28dac3c4ceecd489a8ba4efe33c3138cb034c74f` |
| [results-r2.json](../../tests/fixtures/stabilization/results-r2.json) | `db4950aa1eb688f0ebc2edcb1add03a1c397b48f7db286b05064262f9441302b` |
| [audit-results-r2.json](../../tests/fixtures/stabilization/audit-results-r2.json) | `db4950aa1eb688f0ebc2edcb1add03a1c397b48f7db286b05064262f9441302b` |

Only these source hashes changed within the manifest's source inventory:

| Source | Original SHA-256 | R2 SHA-256 |
| --- | --- | --- |
| `scripts/measure_stabilization.py` | `9de34be354fca91205d6942fd8797d97f66f9cca4e4510a807123e9601b6aeb2` | `926007c76c100ae810bf7b6cd945d213977def3afd2748c9c548e92f7c9eae6b` |
| `tests/test_stabilization_measurements.py` | `fd39ba2381c59f6c3ef63667fb325154d2732d3b289c314256625ddcf62e53ff` | `1b50828844c890f4c6b1972dbebeaee47acf7e73f02df034271f9816fe5312c5` |

The complete manifest differs only in `sources`, `result_path` and the added
`archived_evidence` hash guard. The fixed 14 current rows, 24 historical units,
declaration/injection/detector source, subject sources, patch files, neighbor
requirements and original historical assets are unchanged.

Before the R2 measurement, independent static review passed. The `engine_bytes`
function has the same parsed AST before and after the literal split, and its
actual C01/C02 output hashes still equal the two mutated-source hashes above.
The whole script is **not** claimed to have an unchanged AST: its default
manifest/output paths and archive protection necessarily changed. Seven
non-Scenario preflight checks passed before measurement.

Four new detached subjects were created at the same exact revisions using the
earlier setup recipe, with `uv sync --locked --extra dev --python 3.12.13`
against each subject, and the same two patches were applied. All setup commands
exited 0; the main checkout's environment was not resynchronized. The resulting
Python, PyYAML and pytest versions match the original run.

After explicit architect release, these commands completed with exit code 0:

```sh
.venv/bin/python scripts/measure_stabilization.py --verify
.venv/bin/python scripts/measure_stabilization.py \
  --baseline "$SUBJECTS/baseline" --current "$SUBJECTS/current" \
  --c01 "$SUBJECTS/C01" --c02 "$SUBJECTS/C02"
.venv/bin/python -m pytest tests/test_stabilization_measurements.py \
  tests/test_include_fault_controls.py -q -o addopts=''
```

The measurement created `results-r2.json` once, executing all 52 planned units.
Its aggregate counters are 22 detected, two conformant guards, two killed
engine mutants, two passing engine controls and 24 passing clean neighbors.
There are still no invalid controls or unreached faults. All 52 detailed records,
subject evidence and counters equal the first-run evidence; only the outer
`manifest_sha256` differs. Focused tests: **42 passed** (the previous 41 plus one
archive-preservation check). These repeats add reproducibility evidence, not a
larger distinct-fault denominator or a claimed score improvement.

The independent auditor then ran the same 52-unit command with
`--output tests/fixtures/stabilization/audit-results-r2.json`, exit 0, and
independently reran the focused tests: **42 passed**, exit 0. The R2 developer
and auditor output files are byte-identical. The auditor also verified that
the original and R2 detailed records, subject evidence and counters are equal,
with only the manifest hash changed. No measured obligation was revised between
these runs.

One independent-audit test invocation mistakenly named the nonexistent
`tests/test_named_results_fault_controls.py`; pytest exited 4 without collecting
or running tests. The corrected invocation used the real
`tests/test_include_fault_controls.py` together with the measurement tests and
passed all 42, exit 0. This command-selection error ran no measurement and is
not included in the 52 execution records or any detection denominator.

After R2 independent approval, all four R2 subjects were checked again against
their exact revision/source hashes and full non-ignored status. There were no
unexpected tracked changes or untracked files. Only C01/C02 contained their
specified mutations. Both known patches were reverse-applied, then the four
exact detached worktrees were removed with `git worktree remove`, without
force. Both reversals and all four removals exited 0. The main checkout is the
only remaining worktree. All six original/R2 evidence JSON files and both
patches are retained; no measurement evidence was removed.
