# Background HTTP compatibility verification

Specification: [bounded background HTTP compatibility](browser-background-http-compatibility.md).
Starting main: `29b5e10`. Implementation approved on 2026-11-17. Independent
code and focused browser audit passed; all aggregate checks passed and architect
acceptance is PASS on 2026-11-17.
At that acceptance gate all changes were unstaged and submission was not authorized.
The maintainer subsequently accepted the delivery and separately authorized
submission, PR checks, merge, main CI verification and task-branch cleanup on
2026-11-17. Publication and cleanup are evidenced by the associated PR history.

## Maintainer summary

- Explicit resource paths permit GET/HEAD assets loaded by XHR or Fetch.
- Live background arrays retain their actual bytes without inventing typed evidence.
- Background arrays cannot replace a declared action request or consume a mock fixture.
- Resource permission does not authorize credentials or unknown destinations.
- YAML, format 1, one-level inclusion and business verdicts remain unchanged.

## Implemented scope

`ResourceRoute` and `BrowserNetworkPolicy.resource_routes` add Python-side
resource configuration. Routes are immutable, segment-bounded and disjoint
from API mappings at the same origin. The origin must already be authorized as
page or resource origin. Existing positional policy construction still works.
Credential restrictions run before resource classification. POST, OPTIONS and
preflight receive no resource exception.

The native collector permits valid JSON arrays only for live requests whose
existing initiator evidence established no action ownership. It preserves the
browser's raw bytes, validates query/trace/header policy and retains response
redirect, streaming and CORS restrictions. It creates no invalid RequestSpec,
RecordedResponse or primary traffic. Completion retains the response-header
fence and retires the entry without reading an optional response body.

The one new fixed note, `background request body not represented`, appears once
per context through existing `not_checked`. Core accepts only three distinct
known notes, rejecting duplicates and arbitrary messages. Required checks and
missing-primary errors are unaffected. This is optional diagnostic omission,
not a complete observed response, a new status or an assertion waiver.

Mock arrays, direct and native-await action-associated arrays, non-JSON/scalar
bodies and unsupported multipart forms gain no support. Existing object-shaped
background recordings remain. No WebSocket, EventSource, Worker, redirect,
frame, UI action, download or product-specific behavior is added.

## Measured checks

- Independent unit, core-note and litmus audit: 183 passed.
- Independent real Chromium/server checks: 24 passed.
- Fresh Python 3.11 dev-only suite: 5716 passed, 1 skipped.
- Fresh Python 3.12 dev-only suite: 5716 passed, 1 skipped.
- Full installed-extras suite: 7085 passed, 1 existing dependency deprecation warning
  in 1259.10 seconds; guarded exit 0 and owned-process cleanup completed.
- Lock, repository hygiene (including new files) and diff checks: passed.

Representative commands, with fresh external diagnostic output directories:

```bash
python scripts/run_tests.py --output-dir /tmp/background-http-unit --suite-timeout 300 -- -o addopts= -q tests/test_background_http_policy.py tests/test_background_http_lifecycle.py tests/test_browser_network_identity.py tests/test_browser_diagnostic_work.py tests/test_opensource_litmus.py
python scripts/run_tests.py --output-dir /tmp/background-http-browser --suite-timeout 300 -- -o addopts= -q tests/browser/test_background_http_compatibility.py
python scripts/run_tests.py --output-dir /tmp/background-http-full -- -o addopts= -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Use the repository browser/demo environment for the browser/full commands.
The two dev-only runs used fresh environments with only `.[dev]` installed;
optional browser/demo suites were collection-gated. Exact commands, exit codes
and guarded completion records remain local; no raw credentials or traffic are
published. A core-note regression first rejected the new notice (three failures)
and subsequently passed; development also recorded missing-resource-type and
array-rejection failures. Concurrent browser development runs are not claimed
as a frozen baseline experiment.

## Positive and negative evidence

Independent synthetic servers verify unchanged CSS bytes through Fetch/XHR
GET and the absence of a HEAD body. Ordinary stylesheet loading remains valid.
Unconfigured paths, unrelated origins, forbidden methods and credential-bearing
requests without destination permission do not reach the target service.

Fetch/XHR array requests arrive with exact whitespace, strings, numbers, false,
null and nested object values. The page receives its real response. There are
no manufactured API/primary records; normal object requests still produce typed
diagnostics. Direct and native-await owned arrays fail before delivery. Mock
arrays leave both the service and fixture index untouched. Response redirects,
event streams and CORS denial remain errors.

A real runner test declares a primary request while only an identical-endpoint
background array is sent. The step errors for missing/ambiguous associated
traffic and the domain is not PASSED. The new diagnostic notice cannot hide a
failed assertion or substitute for missing primary evidence. Offline controls
also verify unavailable headers, repeated completions, response budgets and
entry retirement without extra body reads.

## Audit, neutrality and limitations

Implementation and independent audit used different agents. Public tests and
examples use synthetic assets and records; no private product, local paths,
credentials, environment config or raw evidence enters this delivery. Existing
Scenario files, vocabulary, ports and public product-adapter files are unchanged.
The workroom was not accessed. The core still does not import adapters or browser
support. Historical records are preserved.

This repair does not establish universal page compatibility or business UI
acceptance. Unsupported transports still produce explicit errors. An actual
page can therefore progress past these HTTP restrictions and encounter a later
unrelated boundary. Only executed obligations may support an acceptance claim;
normal page opening is not itself a business Scenario pass. Local diagnostic
results and their cleanup flags are retained without being relabeled as passes.

No new YAML, report status, declaration vocabulary, product patch or request
replay was added. Downloads remain paused. No submission occurred during
implementation or audit. The subsequently authorized submission excludes raw
runtime evidence, which remains local.
