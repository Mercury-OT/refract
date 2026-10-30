# Bounded multi-origin browser HTTP: acceptance record

Date: 2026-10-30. Starting main: `3a0b1a5`.
Independent core, browser and consumer audits passed. Architect acceptance passed
after the full sequential suite and scope/source checks below. Public submission
was explicitly authorized by the maintainer; hosted delivery is recorded by the
associated task PR and its post-merge main checks.

## Maintainer summary

- An explicit Python policy permits separate page, API and static origins without changing Scenario YAML.
- Real browser CORS, preflight, headers and request identity remain observable; no HTTP replay repairs a result.
- The ten supported consumer cases pass, including the fixed selector/API-prefix maintenance change.
- Native async association still fails for nine cases; all remain in the measurement denominator.
- This is bounded synthetic integration evidence, not proof of universal compatibility or human cost savings.

## Scope and audited boundaries

The [specification](browser-multi-origin-http.md) is implemented by the optional
browser package, minimal paired network identity in core ports, and a neutral
three-listener records application. The public browser guide and threat model
describe the opt-in behavior and retained limitations. Existing single-origin
behavior remains available. All 65 previously tracked YAML files, declaration
vocabulary, schema version, include depth, dependencies, CI configuration,
MANIFESTO and BRAND remain unchanged.

Native transport uses browser-level Chromium interception, primary-page network
events and out-of-band initiator identities. Connection, credential and API
evidence permissions are distinct. Static/background traffic cannot become action
evidence. Mock API traffic never falls through to a live API. Missing transmitted
trace evidence is not replaced by an invented server trace.

Independent review identified and closed:

| Finding | Correction and evidence |
| --- | --- |
| A popup could send before a primary-page-only guard noticed it. | Browser-level interception aborts secondary-target requests before delivery. Four popup forms and independent frame/srcdoc probes recorded zero destination requests. |
| The diagnostic byte cap omitted retained request bodies. | The cap counts the entire serialized record. A 400 KB background request produces a truncation note and no retained diagnostic. |
| A background disconnect incorrectly poisoned the current action. | Failed unassociated acquisition produces its fixed notice; policy/CORS violations and associated failures remain errors. |
| IPv6 configuration did not match Chromium's canonical address. | Equivalent address forms use the compressed representation. |
| New network identity equality could accept a string subclass in a Recorder copy. | Type-strict recursive comparison guards the identity fields, including real Recorder mutation probes. |
| Outer browser IDs could collide between contexts. | A context namespace qualifies the outer ID; raw browser IDs remain separately checked within their context. |
| The public-list example checked only one of its three claimed records. | Each expected record is now checked. Replacing either remaining record fails while the length assertion still passes. |

Test-only URI fixtures use documentation domains and explicitly constructed
malformed values. No hygiene exception or private-name filter was added.

## Fixed consumer results

Every panel contains the same two implementations and ten Scenario files.
The old helper was actually executed from archived main `3a0b1a5`, with import
paths checked. It rejected the multi-origin application for all twenty units.
The new collector ran against the exact same target source and business checks.

| Case | Old helper, both implementations | Candidate Promise implementation | Candidate native-async implementation |
| --- | --- | --- | --- |
| c01 static readiness | FAILED | PASSED | PASSED |
| c02 all three initial records | FAILED | PASSED | FAILED |
| c03 category filter | FAILED | PASSED | FAILED |
| c04 next page | FAILED | PASSED | FAILED |
| c05 create | FAILED | PASSED | FAILED |
| c06 read created ID | FAILED | PASSED | FAILED |
| c07 update and read | FAILED | PASSED | FAILED |
| c08 delete and list absence | FAILED | PASSED | FAILED |
| c09 anonymous refusal | FAILED | PASSED | FAILED |
| c10 named access | FAILED | PASSED | FAILED |

Each native-async request case really sent HTTP, then failed because no current
action association was available. None was excluded or replaced by a setup error.
Each nonbaseline panel contains 24 actual non-preflight API requests and 15
associated recordings. Background requests are never promoted to fill the gap.

| Panel | Planned/executed | PASSED | FAILED | Elapsed seconds |
| --- | --- | --- | --- | --- |
| Baseline | 20/20 | 0 | 20 | 22.178 |
| Candidate | 20/20 | 11 | 9 | 26.330 |
| Selector/API-prefix maintenance | 20/20 | 11 | 9 | 25.668 |
| Candidate repeat 1 | 20/20 | 11 | 9 | 25.709 |
| Candidate repeat 2 | 20/20 | 11 | 9 | 25.758 |

All 100 execution units were independently recounted. Scenario and consumer
hashes are identical across panels. Candidate engine hashes are identical across
its four panels. Repetition retains the same per-case statuses; this small sample
does not establish a general reliability rate or performance benchmark. The old
helper's fast rejection is not a comparable successful-run latency.

### Cost accounting

Python physical lines touched by non-comment tokens include docstrings and
embedded data. JavaScript and YAML counts are nonblank lines, reported separately.

| Category | Count |
| --- | --- |
| Product adapter Python | 61 |
| Reusable browser package Python, total including existing code | 1206 |
| Target application Python | 151 |
| Measurement harness Python | 167 |
| Consumer test Python | 103 |
| Promise/native-async JavaScript | 26 / 31 |
| Ten Scenario files, YAML | 532 |
| Target mappings | 14 controls, 1 page, 1 API endpoint, 1 static origin, 1 credential origin |

The maintenance variant changes two explicit configuration fields: selector
prefix and API prefix. Human authoring, diagnosis and review minutes were not
measured. Code size is not evidence of time saved; this one change does not
predict general adapter maintenance cost.

### Reproduction and source identities

Use a shell with the repository root as its current directory. Equivalent
reproduction commands follow; the executed panel and recomputation commands all
returned exit code 0. The panel command's zero exit means the complete measurement
was recorded, not that every business Scenario passed. Its JSON retains every
non-passing row and synthetic request data.

```sh
mkdir -p /tmp/browser-baseline-source
git archive 3a0b1a5 | tar -x -C /tmp/browser-baseline-source
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="/tmp/browser-baseline-source:$PWD" \
  .venv/bin/python -B examples/browser_multi_origin/run.py \
  --legacy --expected-engine /tmp/browser-baseline-source \
  --label baseline-3a0b1a5 --output /tmp/browser-baseline.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label candidate --output /tmp/browser-candidate.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label maintenance --maintenance --output /tmp/browser-maintenance.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label candidate-repeat-1 --output /tmp/browser-repeat-1.json
uv run --frozen python -m examples.browser_multi_origin.run --expected-engine . --label candidate-repeat-2 --output /tmp/browser-repeat-2.json
uv run --frozen python -m examples.browser_multi_origin.measure --baseline /tmp/browser-baseline.json --candidate /tmp/browser-candidate.json --maintenance /tmp/browser-maintenance.json --repeat /tmp/browser-repeat-1.json --repeat /tmp/browser-repeat-2.json --output /tmp/browser-cost.json
```

The recorded run used the same commands with `.venv/bin/python -B` for candidate
execution and a different temporary baseline-directory name. Interpreter imports
and all input hashes were verified before and after each run. For the sorted
relative-path-to-SHA256 maps, SHA256 of UTF-8 `json.dumps(map, sort_keys=True,
separators=(',', ':'))` is:

- 17 consumer files: `7045a5a04e8ff9dae5f1a9674525f0e0001c3e406a92afb411d8d0f96a6296cc`.
- 43 baseline engine files: `57e33fde8eb919ccaac0c3e0527eb822150d2495d15b169d566c64f6952ba2ff`.
- 45 candidate engine files: `3be7481e33746bafce4e68626aaf70fc40aee987897c3c46bacbd0dc8c47df47`.

Raw measurements are local generated artifacts, not a general safe-to-publish
export format. The committed harness regenerates them from public synthetic
inputs and rejects omitted/duplicate units or changed Scenario hashes.

## Verification and acceptance

Local browser verification used Python 3.12.13, Playwright 1.62.0 and its Chromium
151.0.7922.34 (revision 1234). The fresh core environments used Python 3.11.15 and
3.12.13 with only the dev extra.

- Developer transport/consumer suite: 89 passed.
- Independent browser transport/default-support suite: 118 passed; ten separate
  actual Chromium probes plus the IPv6 probe also passed.
- Independent core scope: 289 focused checks, seven additional probes and a real
  Chromium namespace check passed.
- Independent consumer scope: all five measurement panels and source hashes
  verified; the original two-record substitution probe now fails correctly.
- Test-only origin fixture cleanup: 105 targeted checks passed; independent
  selected identity/policy/transport recheck: 117 passed.
- Fresh dev-only Python 3.11 and 3.12 environments: 4059 passed, 1 skipped each.
- Core litmus and stabilization documentation/boundary sentinels: 90 passed.
- Full sequential suite (`PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest`):
  4725 passed, one existing third-party deprecation warning, 587.01 seconds.
- Lock, repository hygiene and diff checks: passed. Staged-source checks are
  repeated as part of the authorized submission sequence.

The shared browser test helpers now use a 5000 ms default timeout, matching the
existing helper default. Tests with explicit short deadlines retain those values.
No production timeout or CI parallelism setting changed.

Remaining limits are explicit: Chromium only; no native-async/timer attribution;
no redirect, popup/frame, worker, WebSocket or event-stream workflows; no native
mock preflight; unavailable complete native-mock response headers; no trace-based
server-state proof without an actual trace. Associated response acquisition is
bounded to 8 MiB and its deadline. Retained diagnostics are bounded to 100 records
and 256 KiB of serialized records, not all browser memory.

Only public synthetic source was used. No private workspace or product was
accessed. This acceptance concerns the approved bounded mechanism and observed
results; it does not close broader browser compatibility or adoption questions.
