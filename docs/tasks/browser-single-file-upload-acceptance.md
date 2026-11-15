# Browser single-file upload verification

Specification: [browser single-file uploads](browser-single-file-upload.md).
Expression, failure rules and proof-first implementation were approved on
2026-11-15. Starting main: `492f0e3`. Status: PASS. Development, independent mechanism/core and consumer audits,
and architect acceptance passed on 2026-11-15. The maintainer authorized
submission and merge after acceptance and successful hosted checks. Publication,
main CI and branch cleanup are separately evidenced by the associated PR history.

## Maintainer summary

- A page can select one frozen local file, then submit it with a separate click.
- Core checks actual selected bytes and independently captured outgoing bytes.
- Two neutral pages verify actual storage readback, including binary and empty files.
- Missing or ambiguous evidence cannot become a pass; wrong observed values fail.
- Format 1, one-level inclusion and existing result meanings remain unchanged.

## Delivered boundary

Selection uses `do: select_file`, a literal logical target, and a single
`file: {path, sha256}` descriptor. A separate click declares the expected
single `expect.request.files` field. These are separate obligations: selecting
the right file does not establish what the application subsequently sends.
Existing source-relative asset containment, hash checks and composition budgets
apply before execution, including child Scenarios and Flow nodes. Frozen bytes
are used without reopening a source path. Expansion exposes descriptors only.

The driver opts into selection and file-request observation separately. Core
signs the actual immutable file data into the action permit and validates a
strict, single-target selection receipt. Action ports receive no expectations.
The browser helper selects memory-backed input bytes, then reads the connected
input's actual File bytes. Input/change events are not claimed to be trusted
native chooser interactions. A standard extension table supplies File.type;
unknown extensions use application/octet-stream without modifying content.
Browser-ambiguous double-quote/encoded quote or line-break names fail before UI
actions; existing API filename support is unchanged.

Actual submission requires complete browser-level native multipart segments,
existing trusted click/native-await ownership and paired response identity.
Selected bytes, expected bytes and source files never fill missing capture.
Synthetic, background, old-action and selection-triggered traffic cannot become
Submit evidence. Selection auto-upload is unsupported. Complete missing/wrong
file observations fail request checks. Missing binary segments, malformed or
ambiguous framing, unsupported attribution, over-limit evidence or mutation
produce ERROR. Errors cannot reverse effects already produced by a product.

The helper bounds files, raw multipart size, framing overhead, part/segment
counts and retained diagnostics. It does not bound Chromium's earlier memory
allocation for a protocol event. Default file and composition budgets remain
10 MiB and 64 MiB. Empty named files are valid. An empty unselected-input
placeholder is observed as no file; an unnamed nonempty part is unsupported.

## Real browser and server evidence

The Documents page builds FormData(form) and uses fetch. Records uses different
selectors, request fields and response shape with appended File and asynchronous
XHR. Their shared helper performs capture; product adapters only map actions
and observations. Separate server MIME parsing stores received bytes on disk,
then opens those files for the final GET. Tests also inspect saved bytes through
a separate HTTP client. Source manifests pin the synthetic page/server code;
byte equality was checked, not historical authorship or approval chronology.

Live e2e executes all five steps. Separately authored frontend-only documents
use explicit mocked responses and zero live API calls; they do not claim server
persistence. Backend performs the explicit upload/read declarations, leaves UI
obligations unchecked, and contract reuses those recordings without another
request. A selection-only backend/contract is EMPTY. Frontend still rejects the
complete example's explicit API read; no projection silently trims that example.

Controls cover text, binary NUL/high bytes, PNG, PDF and empty files; frozen
input after source replacement; wrong names, fields, bytes and truncation;
missing files; false successful responses; and corrupted storage readback.
These establish immediate readback, not media rendering or long-term durability.

## Independent audit and corrections

Before implementation, 16 native multipart captures exactly matched actual
server bytes. Twelve production-association controls passed, with 18 captured
associated/diagnostic bodies matching the server. Separate disk-backed input
probes exposed missing native file segments, including empty files: these are
explicitly refused rather than reconstructed. Exact 10 MiB and over-limit
capture controls verified decoded byte accounting.

Independent mechanism/core review found and closed one P1. An early closing
boundary or padded delimiter could be retained as file bytes although the
server parsed a shorter file. Three independent probes reproduced the mismatch,
including actual Chromium/server disagreement. The parser now recognizes those
delimiter lines and rejects unsupported framing before delivery. Shipped
regressions preserve ordinary near-boundary binary data and reject ambiguous
forms. An additional 264-variant differential accepted 192 and rejected 72, with
zero accepted-value mismatches against independent MIME parsing.

The mechanism audit passed 539 focused tests, then 49 post-fix targeted tests.
Final ownership controls passed 15 real-browser tests. Consumer audit separately
passed all 30 shipped consumer tests and 24 independent probes, covering actual
input bytes, file freezing, storage reads, mock isolation, mutation rejection,
safe diagnostics and cleanup. Counts overlap and must not be added together.
These audits support cooperative adapter evidence; they do not prove resistance
to hostile Python code or arbitrary page instrumentation tampering.

Full offline checking found ten failures in one older review-equivalence test:
its strict Step field inventory omitted the new file fields. The inventory was
extended and each field is explicitly checked absent for that frozen file-free
exercise; all 29 exercise tests passed independently. No inventory safeguard
or equivalence assertion was removed. The initial in-progress full run was
stopped with owned-resource cleanup, then restarted after refreezing. Developer
consumer assertions were also corrected to respect existing contract-level
reporting rather than expect nonexistent contract StepResults. A new Flow
test initially omitted required explicit user mappings; its fixture was fixed
without changing the established mapping rule. One mock browser fixture also
needed its declared CORS response header; the browser policy was not relaxed.
No failure was waived. Runtime code was unchanged by the review-inventory repair.

## Final verification

Actual final acceptance commands, from the public repository (output redirection
omitted). The two temporary Python environments were freshly installed with
only `.[dev]`; the repository environment includes the demo/browser dependencies.
Guard output directories retain these runs and must be replaced for a new run.

```sh
.venv/bin/python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-full-final2 -- -o addopts='' -q
/tmp/refract-browser-upload-core311/bin/python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-core311-final2 --suite-timeout 600 -- -o addopts='' -q
/tmp/refract-browser-upload-core312/bin/python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-core312-final2 --suite-timeout 600 -- -o addopts='' -q
.venv/bin/python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-consumer-audit/consumer-suite --suite-timeout 900 -- tests/browser/test_browser_file_upload_consumers.py -q
.venv/bin/python scripts/run_tests.py --output-dir /tmp/refract-browser-upload-final-docs --suite-timeout 120 -- tests/test_stabilization_documentation.py tests/test_opensource_litmus.py -o addopts='' -q
.venv/bin/refracto validate examples/browser_file_upload/documents.yaml --expand
.venv/bin/refracto validate examples/browser_file_upload/records.yaml --expand
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

The final documentation/litmus panel passed **63 tests** after the verification
record was added. The native changed-file and broader panels are retained in
`/tmp/refract-browser-upload-native-frozen-20261115` and
`/tmp/refract-browser-upload-native-final-20261115`. Independent audit panels
remain separate from shipped-suite totals.

The final full suite passed **6957 tests**, no skips, with one existing
Starlette/httpx deprecation warning, in **1232.94 seconds**. Its guard exited 0,
needed no diagnostic intervention and confirmed complete cleanup. Fresh Python
3.11 and 3.12 environments installed with only `.[dev]` each passed **5612 tests**,
with one optional collection skip, in **48.35** and **48.43 seconds** respectively.
Those skips are not browser evidence; the full suite ran actual Chromium.
The final browser changed-file panel passed **110 tests**; its broader native,
form and lifecycle panel passed **277**. Documentation, litmus, review and
existing uploads are included in the full suite. All reported guarded passes
exited 0 with complete cleanup. The separate runnable example passed all six
consumer/projection combinations. These overlapping panels are not extra unique
test counts.

Final runtime/test/asset files match the independently reviewed 48-file freeze.
Lock, repository hygiene and diff checks passed. Information-source review also
covered every untracked new file and binary fixture, rather than relying only
on the tracked-file hygiene script. Final documentation records actual results;
publication checks will run the complete submitted tree.


Public changes derive only from existing public code and neutral synthetic
examples. No private workspace or product was accessed or changed. Dependency,
CI, assertion vocabulary and schema version were not changed. File-free adapter
behavior remains covered by regression. No hidden-input proxy, native chooser,
directory, multiple-file request, automatic upload, navigation submission,
streaming, chunking, arbitrary browser compatibility, media playback or actual
product adoption is claimed.
