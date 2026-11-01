# Same-page Enter form submission: verification record

Date: 2026-11-01. Starting main: `b6107be`.
Specification: [bounded same-page form submission](enter-form-submission.md).
Status: development, both independent audits and architect acceptance passed.
The final full suite passed 5400 tests with one existing dependency warning and
no skips. Hosted checks and publication are evidenced separately by the authorized
task PR, main CI and branch cleanup; this record preserves local verification.

## Maintainer summary

- The existing Enter operation can reach an ordinary form's submit handler.
- The product cancels its own navigation; the helper does not repair focus,
  call submit or replace a missing request with an API action.
- One unchanged Scenario and adapter are reused on two new form-handler variants.
- Programmatic submissions and implicit-click/background traffic cannot substitute
  for submit-handler evidence. The same existing failure rules apply.
- Core, YAML, ports, vocabulary, include depth and prior normal targets remain
  unchanged; object absence and Flow are outside this task.

## Feasibility gate and mechanism

Initial real-Chromium observations established the native sequence: keydown,
keypress, default submitter click, submit, keyup. Seven event-order probes also
showed that requestSubmit can produce a trusted submit event without Enter;
trusted alone therefore cannot be the association rule.

The scratch collector matrix passed 34 cases, then 36 cases including native
input-submit controls and external form-owned buttons. A final 41-case gate
passed before helper implementation (37.30 seconds, exit 0), adding native/legacy
XHR, explicit mocks and validation rejection. The command was
`.venv/bin/python -m pytest -o addopts='' -q /tmp/refract-enter-form-probe/test_candidate.py`.
Scratch commands are exploratory records; retained repository tests are the
repeatable delivery artifact.

The helper pins actual input/form/default-submitter objects and validates the
native event chain. Programmatic dispatch/click/submit/requestSubmit establish a
null invocation scope during a press, including nested callbacks and supported
async continuations. An implicit-button click is only a transition; its requests
do not gain submit-handler origin. The product must cancel the actual submit,
verified after dispatch, including onsubmit return false. A helper navigation
guard cannot supply that cancellation.

Browser validation or product cancellation may leave a valid key receipt with
no submitted request. Core's existing request requirement then decides whether
evidence is missing. A button disabled after a verified submit does not rewrite
the event's history; input identity and focus remain strict through collection.

## Consumer and public sources

The new examples/ui_enter_form target uses a native form and two product-owned
submit handlers. The listener uses a Promise chain; the property handler cancels
navigation synchronously and uses native await before fetch. They share the
existing example's HTTP service and dataset, and are reported as two variants,
not two independent products or proof of adoption savings.

Normal target sources were written and frozen before the consumer wrapper and
fault tests: three new app/script hashes and the shared service hash appear in
target-sources.json. The original Scenario, adapter, target and run wrapper stay
byte-identical. The reused Scenario SHA-256 is
`4456e00a0abbdb29a341c9aab7ee6f5047dcd2d7370f8174c70fdf22918eae07`.
Faults are separate test subclasses; the adapter does not modify the target.

Developer verification passed all 19 consumer cases. Both live CLI variants
returned PASSED, with one real search request, the checked response and rendered
rows, one Enter down/up pair, one user/session/context and one close, zero API-port
sends and no degradation. Ignored submission and validation produce ERROR for
missing required requests; wrong query/response/rendering produce FAILED.
Programmatic or wrong-form requests and focus theft cannot pass the Scenario.

## Independent review findings

The independent consumer review passed 25 checks (the 19 consumer tests plus six
additional live controls): duplicate identical requests cannot be arbitrarily
selected; implicit-click traffic and correct-looking rendering cannot replace
missing submit-handler evidence; and uncancelled navigation cannot pass.

That reviewer also raised a possible ordinary-click regression. The mechanism
reviewer confirmed it with a baseline/current comparison: two original legacy/
native cases passed against b6107be instrumentation and both failed against the
initial change. An ordinary button click calling requestSubmit with a property
onsubmit handler lost its earlier request origin because the newly wrapped
property introduced a null scope outside Enter. This was a blocking compatibility
finding, not a product fault. The correction scopes the new property behavior at
invocation to Enter, preserving the original non-press caller scope and return
value. This also handles the same callback reused across properties and an
installed handler persisting from Enter to a later ordinary click. Developer
verification passed 77 mechanism cases plus eight independent baseline/current
comparison cases before the final independent recheck below.

The final mechanism reviewer independently passed 55 real-Chromium checks in
51.27 seconds, exit 0: ten causality probes, eight compatibility/baseline/shared-
callback checks, eight cancellation/target checks, twelve prior Enter/idle/action
guards, five native-await controls, eight object-navigation controls and four
raw-transport rejection controls. The ordinary-click finding is closed in both
transports, including Enter followed by another click. No remaining mechanism
blocker was reported. Audited source hashes are
`9199d75b6fc1112ed178f8617f396cef22965054aab92cb29133d3f57376d8da`
for _instrument.py and
`79ded71f108881af3cef0b095a531486c7732a290b1718eab01959ddf1aff827`
for _key_press.py.

The independent consumer reviewer then repeated all 25 checks against those exact
corrected helper hashes: 25 passed in 19.80 seconds, exit 0. Its delta review
confirmed Enter isolation and non-press compatibility; all four new/shared target
hashes and six original Scenario/adapter/target/runner files remained identical.
Both independent audits passed with no open blocking finding. The subsequent
architect full-suite verification also passed, as recorded below.

## Commands and results

All repository commands run from the public repository. Optional browser checks
require the installed Chromium. No private workspace is accessed.

| Command / environment | Actual result |
| --- | --- |
| `.venv/bin/python -m pytest -o addopts='' -q /tmp/refract-enter-form-probe/test_candidate.py` | Final feasibility: 41 passed, 37.30 seconds, exit 0 |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q tests/browser/test_enter_form.py` | Before compatibility correction: 65 passed, 59.87 seconds, exit 0 |
| `.venv/bin/python -m pytest -o addopts='' -q tests/browser/test_enter_form.py /tmp/refract-enter-form-probe/test_nonpress_compatibility.py` | After correction: 85 passed (77 mechanism + 8 comparison cases), 78.19 seconds, exit 0 |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q tests/browser/test_enter_form_consumers.py` | Consumer developer check: 19 passed, 14.59 seconds, exit 0 |
| `uv run --locked --no-sync python -m examples.ui_enter_form.run` | Both live variants PASSED, exit 0 |
| `PYTHONDONTWRITEBYTECODE=1 uv run --locked --no-sync python -m pytest -o addopts='' -q tests/browser/test_enter_form_consumers.py /tmp/refract-enter-form-independent-consumer.py` | Independent consumer review: 25 passed, 20.34 seconds, exit 0; before compatibility correction |
| Same independent consumer command after correction | 25 passed, 19.80 seconds, exit 0 |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q tests/test_stabilization_documentation.py tests/test_opensource_litmus.py` | 52 passed, 0.61 seconds, exit 0 |
| Dev-only Python 3.11: `python -m pytest -o addopts='' -q` | 4351 passed, 1 expected optional-dependency collection skip, 9.88 seconds, exit 0 |
| Dev-only Python 3.12: `python -m pytest -o addopts='' -q` | 4351 passed, 1 expected optional-dependency collection skip, 9.92 seconds, exit 0 |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q` | Final architect suite: 5400 passed, 1 existing Starlette/httpx warning, no skips, 895.96 seconds, exit 0 |
| `uv lock --check`, repository hygiene, `git diff --check` | Passed |

The final independent mechanism command was:

```sh
uv run --locked --no-sync python -m pytest -o addopts='' -q \
  /tmp/refract-enter-form-probe/test_independent_boundary.py \
  /tmp/refract-enter-form-probe/test_nonpress_compatibility.py \
  tests/browser/test_enter_form.py::test_cancelled_submit_stays_same_page_despite_target_attribute \
  tests/browser/test_enter_form.py::test_uncancelled_target_cannot_pass_by_navigation_guard \
  tests/browser/test_enter_press.py::test_unsupported_transitions_fail \
  tests/browser/test_enter_press.py::test_post_press_idle_navigation_rejected_before_next_action \
  tests/browser/test_enter_press.py::test_next_explicit_action_preserves_existing_behavior \
  tests/browser/test_native_await.py::test_null_nested_event_scope_blocks_outer_trusted_identity \
  tests/browser/test_native_await.py::test_same_helper_and_same_request_background_never_substitute \
  tests/browser/test_object_navigation.py::test_document_navigation_retains_actual_receipt_and_next_action \
  tests/browser/test_audit_regressions.py::test_unsupported_beacon_and_native_form_never_send_backend_data
```

Result: 55 passed, 51.27 seconds, exit 0. Temporary independent probes are separate
from the committed regression suite; the command/output are retained in the
independent audit record, not claimed as an additional repository log file.
Early scratch setup mistakes (assuming same-form recursive submission and
double-applying a candidate patch) were discarded, not counted as passing checks.

The full environment used Python 3.12.13, pytest 9.1.1 and Playwright 1.62.0.
The final readiness-only adjustment replaced a 30 ms sleep in programmatic
negative controls with actual response completion; its twelve cases passed before
the independent audits and final full suite. An earlier 150-case focused run was
before final cancellation/compatibility refinements and is not substituted for
the final results above.

## Accepted scope and information review

The 19 accepted public files are two browser implementation modules, three browser
test files, seven new consumer files and seven specification/contract/delivery
documents. Source and examples are neutral synthetic material or reuse existing
public examples. No private product, workspace, credential or internal evidence
is used. Source pins identify the actual checked files, not independent approval.

An 83-file baseline comparison confirmed unchanged core, vocabulary, declarations,
dependencies, CI, manifesto/brand files and prior normal targets. Both independent
audited helper hashes match the final source. All task changes remain within the
accepted file list. No private workspace was accessed. A local acceptance does
not substitute for the required associated PR/main CI and cleanup checks.

## Limits

One main document, a unique already-focused editable text/search input and a
supported native default submitter are required for native form submission.
Submission without that control, or through an image submitter, is unsupported.
Actual navigation, redirects, frames, popups,
downloads, other keys, uploads and automatic focus repair remain excluded.
Background and programmatic submissions may have real product effects; they are
not promoted into action evidence and cannot repair a missing declared request.
Observed errors do not roll back effects already produced.

This remains cooperative browser/adapter consistency, not hostile-page
attestation, independent server tracing or proof of every business obligation.
UI checks cover the expected name and one known excluded name. Backend and
contract cannot independently prove keyboard/form behavior; mock passes are not
live-product evidence. No new language expression or report state is introduced.
