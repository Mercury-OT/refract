# Browser form request observation: local acceptance

Date: 2026-10-25. Result: **PASS for the bounded task**.
Specification: [browser form request observation](browser-form-request-observation.md).
Starting main: `f155ad50acd3d3d2c42ae3963a48e80690d63ac4`.
The maintainer authorized development, independent audit and local acceptance.
No staging, commit, push, PR or publication is authorized. No private workspace
was accessed or modified. This record establishes local results, not hosted CI.

## Delivered behavior and evidence

BrowserSupport now decodes ordinary UTF-8 URL-encoded fetch/XHR bodies using
actual Content-Type observations and request bytes. Business fields remain
strings, without consulting Scenario expectations to choose their values or
types. Duplicate decoded names, bad encoding and ambiguous or unsupported form
Content-Type fail before live forwarding or mock consumption. The previous
non-form JSON-object/null path remains unchanged.

The executable [mixed request example](../../examples/browser-form-requests/README.md)
opens a synthetic page, fills a value, submits it as JSON, and submits it as an
ordinary form. The same existing-format YAML passes strict top-level RunReport
checks in frontend mock and live e2e, without degradation. Live server receipt
verifies original bytes and Content-Type; mock verifies independent fixture
responses and zero API forwarding. Actual fetch and XHR are exercised.

Negative controls detect wrong/missing fields and string-versus-number, boolean
or null mismatches. Ordinary assertion failures still allow later independent
actions; decoding errors remain ERROR and block subsequent UI actions through
the existing context rules. Background traffic stays diagnostic, altered
request/response pairing is rejected, and sensitive sentinels do not appear in
new error messages or final report repr. Repeated endpoints retain distinct
request identities and mock fixture associations.

Current Chromium/Playwright exposed `post_data_buffer=None` for an empty
URLSearchParams body, an empty string and a null body; the server received empty
bytes. Evidence therefore retained None. Offline tests separately establish
that an available empty byte string decodes to an empty mapping. No missing
browser evidence is reconstructed from expected values.

## Verification

All final verification commands exited 0. No runtime repair was required by audit.

| Check | Actual result |
| --- | --- |
| Full regression, including real Chromium | 4164 passed, no skips, one existing Starlette/httpx warning; 480.29 s |
| Fresh dev-only CPython 3.11.15 | 3594 passed, one optional Demo collection skip; 43.87 s |
| Fresh dev-only CPython 3.12.13 | 3594 passed, one optional Demo collection skip; 43.99 s |
| New real-browser consumer tests | 62 passed, no skips; 51.20 s |
| New offline decoder plus existing lifecycle/user/collection checks | 85 passed; 0.08 s |
| Existing real-browser support and audit regressions | 75 passed, no skips; 63.60 s |
| Independent focused review | 121 new decoder/browser cases passed; example validation passed |
| Independent temporary probes | 5000 UTF-8 roundtrips, 62 route probes and five type-mismatch controls passed |
| Final completion-order-independent test correction | 2 passed, 60 deselected; 1.70 s |
| Example validation and expansion | Passed: four steps, two requests, four response checks |
| Lock, repository hygiene, whitespace and index checks | Passed; index empty |

Before runtime implementation, six actual-browser form/mixed-Scenario tests
failed against the existing JSON-only decoder. Development corrected two test
issues: a reserved pytest parameter name and case-sensitive header lookup.
Audit and architect review also identified a test-only ordering assumption:
concurrent live requests need not complete or reach the server in source order.
The new test now associates pairs by observed values/identities and compares
server receipt without arrival-order assumptions. The full run had already
collected the preceding version of that test; both corrected cases were run
separately and passed. Runtime and page dispatch were unchanged by this fix.
Independent review confirmed the correction and closed the note.

Reproduction commands from the public repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 \
  uv run --locked --no-sync pytest -o addopts='' -q --tb=short
uv run --locked --no-sync pytest tests/test_browser_form_body.py \
  tests/browser/test_form_requests.py -o addopts='' -q
uv run --locked --no-sync pytest tests/browser/test_form_requests.py \
  -k repeated_form_endpoint -o addopts='' -q
uv run --locked --no-sync refracto validate examples/browser-form-requests/mixed_requests.yaml
uv run --locked --no-sync refracto validate examples/browser-form-requests/mixed_requests.yaml --expand
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Each isolated core environment used a different temporary directory and only
the dev extra, without Playwright, httpx, FastAPI or other Demo dependencies:

```sh
UV_PROJECT_ENVIRONMENT=<fresh-environment> uv sync --offline --locked --extra dev --python <3.11-or-3.12>
PYTHONDONTWRITEBYTECODE=1 <fresh-environment>/bin/python -m pytest \
  -o addopts='' -q -rs --tb=short -o cache_dir=<fresh-cache> --basetemp <fresh-tests>
```

The optional Demo collection skip is expected in those environments; it does
not substitute for full-environment browser evidence. Import litmus and existing
executable documentation checks passed as part of the full and offline suites.
Temporary independent probes are additional review evidence, not retained tests
or a claim of exhaustive input coverage.

## Boundaries and acceptance

Independent audit: **PASS**, no unresolved findings. Architect acceptance:
**PASS**. The source review covered all changed and new public files, including
the synthetic page and server. The routine hygiene script checks tracked files;
untracked additions also received source and generic path/host/language checks.
No private source, name, path, product sample or measurement was introduced.

Schema version 1, core, ports, vocabulary, all existing Scenario files,
dependencies, CI, MANIFESTO and BRAND are unchanged. The new example uses existing
syntax. No encoding selector, media-type assertion or API transport capability
was added. Native form navigation, multipart/files, arbitrary body formats and
unsupported asynchronous origins remain outside this helper's supported scope.
Raw header pairs remain sensitive; the decoded body is not a retained packet
capture. Contract was not selected by the mixed UI example and is not an
independent encoding observer. These results do not prove private-product
adoption, malicious-adapter resistance or compliance with every HTTP format.

Accepted scope (12 files):

```text
docs/browser-support.md
docs/roadmap.md
docs/tasks/browser-form-request-observation.md
docs/tasks/browser-form-request-observation-acceptance.md
examples/browser-form-requests/README.md
examples/browser-form-requests/mixed_requests.yaml
refracto_browser/_request_body.py
refracto_browser/_support.py
tests/browser/app.html
tests/browser/conftest.py
tests/browser/test_form_requests.py
tests/test_browser_form_body.py
```

Main remains at the starting commit. All changes are unstaged and uncommitted.
The priority index also corrects the previous time task to its already-delivered
PR #33/main `f155ad5` state; its historical acceptance record is preserved.
Separate maintainer submission authorization is still required.

## Subsequent submission authorization: 2026-10-26

After reviewing and accepting this completed task, the maintainer separately
authorized submission of exactly the 12 files listed above: create a dedicated
public task branch, commit and push it, open a pull request, merge only after
green PR checks, verify merged main CI, then remove both task branches and
synchronize a clean local main. The private workspace remains untouched.

Earlier no-submission and unstaged-state statements describe the local
acceptance stage and remain historical. This later instruction authorizes
publication of the accepted scope only. It does not authorize new capabilities
or YAML changes. Hosted CI, merge and cleanup outcomes are established by the
resulting pull request and workflow records, not this pre-submission record.
