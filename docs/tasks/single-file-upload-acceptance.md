# Fixed single-file API upload verification

Specification: [single-file uploads](single-file-upload.md), expression and
implementation authorized on 2026-11-10. Starting main: `18d9b2e`.
Status: PASS. Development, independent core and consumer audits, and architect
acceptance passed on 2026-11-11. The maintainer authorized submission and merge
after these gates and successful hosted checks. Publication, main CI and branch
cleanup are separately evidenced by the associated PR/commit history.

## Maintainer summary

- An explicit API request can upload one reviewed local file as unchanged bytes.
- Text, PNG, PDF, other binary and empty assets have actual HTTP controls.
- File pins, bounded snapshots and driver opt-in prevent silent substitutions.
- Documents and Records examples read saved content after a real upload.
- Browser selection, download support, media playback and adoption claims remain out of scope.

## Delivered boundary

`do.request.files` has one literal field containing exactly `path` and `sha256`.
The source-relative asset is checked and frozen before any action, including
assets inside pinned children and Flow nodes. The default host limits are
10 MiB per file and 64 MiB per loaded composition; the same canonical source
pathname is counted once, while different paths count separately. Exact limits
and empty files are valid; symlinks, unsafe paths, nonregular files, bad hashes
and over-limit assets fail. Secure directory-relative operations are required;
unsupported platforms fail explicitly rather than weakening containment.

Resolvers receive only owned operation data and immutable UploadFile values.
API drivers must explicitly opt in. Frozen data survives parameter binding,
include/Flow expansion, recordings, normalization and contract checks. Neither
senders nor resolvers reopen paths. Upload body fields are strict strings.
The format remains 1; inclusion remains one level; assertion vocabulary and
business result semantics are unchanged. File-free drivers remain compatible.

Backend and live e2e explicit API actions share this path. These API actions do
not verify browser selection or browser upload. Frontend still rejects direct
API actions; contract reuses recordings without another upload. Expansion and
change-impact review preserve file descriptors without printing file contents.

## Real HTTP consumers and negative controls

The two standard-library consumers use different paths, file/text fields and
response shapes. The sender and server are separate modules connected through
loopback HTTP. The server independently parses multipart, saves received bytes
to a temporary file and rereads that file for later metadata requests. Tests
also use a separate HTTP client to inspect raw saved bytes. No client-supplied
digest is treated as observed server content, and non-JSON responses are not
fabricated into RecordedResponse JSON.

All 44 consumer tests pass, including text, valid synthetic PNG/PDF, arbitrary
binary and empty files; unchanged filename/bytes; actual trace/header receipt;
backend/contract and API e2e; replaced source after loading; wrong, truncated or
dropped transmitted bytes; missing text fields; corrupt saved content; and false
201 responses. Intended-metadata echoes do not rescue these faulty consumers.
The executable example reports both Scenarios PASSED with four real HTTP
requests and two saved uploads.

## Independent audit and corrections

The independent core auditor passed 84 extra adversarial probes outside the
repository. These cover secure open/read bounds, source changes, per-file and
composed budgets, strict capability preflight, wrong runtime dependencies,
resolver/recording/normalizer/contract tampering, child path ownership, Flow,
review/expansion and safe diagnostics. Independent consumer review verified
actual storage reads, fixture structure, credentials, wire headers and cleanup.
These panels overlap repository tests and must not be added as unique coverage.

Findings were corrected before final verification: the live e2e API wrapper now
forwards file capability, method-ownership errors no longer echo a resolver's
sensitive value, unsupported secure-open platforms fail safely, and the direct
API helper validates its supplied step before authentication. Default repr also
hides raw/normalized response payloads which can contain uploaded content.
Four real-readback sentinel tests cover this last correction. Explicit field
access and arbitrary serialization still expose actual data; this is not a
general redaction system.

The first offline run exposed two existing concurrency test doubles that did
not accept the newly optional loader keyword. Their signatures were updated
without changing concurrency assertions. An in-progress full run was stopped
with complete owned-resource cleanup; the final runs below use the corrected
frozen code. No test failure was waived.

## Final verification

Run from the public repository, using fresh guard output directories:

```sh
python scripts/run_tests.py --output-dir /tmp/refract-upload-full-final2 -- -o addopts='' -q
python scripts/run_tests.py --output-dir /tmp/refract-upload-core --suite-timeout 600 -- -o addopts='' -q
python -m pytest tests/test_file_upload_core.py tests/test_file_upload_consumers.py -q
python -m examples.file_upload.run
refracto validate examples/file_upload/documents.yaml --expand
refracto validate examples/file_upload/records.yaml
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

The final full suite passed **6670 tests**, no skips, with one existing
third-party Starlette/httpx deprecation warning, in **1144.29 seconds**. The
guard exited 0, needed no diagnostic intervention and confirmed complete
cleanup. Fresh Python 3.11 and 3.12 environments installed with only `.[dev]`
each passed **5425 tests**, with one optional collection skip, in 49.02 and
48.42 seconds. Those skips are not browser execution evidence; the full suite
executed real Chromium. New repository coverage is 107 core and 44 consumer
tests. Documentation, review-equivalence and litmus checks passed as part of
the final suite. Lock, hygiene and both diff checks passed.

The complete staged-file checks later caught two new-fixture issues omitted by
the earlier unstaged checks: a negative URL example used a non-allowlisted host,
and Git treated the PDF cross-reference whitespace as text. The URL now uses
the standard example domain with the same rejection behavior. The PDF has a
legal binary comment and recomputed offsets; independent `pdfinfo` inspection
confirms one valid page. All **151 upload tests** passed again after these
fixture-only repairs. Runtime code was unchanged; final hosted suites run the
submitted fixture bytes. No hygiene rule or test was disabled.

Runtime/test bytes matched the reviewed freeze. Final documentation records
actual results and clarifies the tested platform boundary. No dependency, CI,
assertion vocabulary, private workspace or product was changed or accessed.
All public assets and claims derive from neutral synthetic material and public
code. Broader compatibility, media validity and real-product adoption remain
unverified. Core pairing checks cooperative adapter evidence; it cannot attest
arbitrary in-process code or prove persistence merely from a successful response.
