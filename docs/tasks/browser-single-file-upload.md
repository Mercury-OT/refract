# Browser single-file selection and submission

Status: the maintainer approved the expression, failure rules and proof-first
implementation on 2026-11-15. Starting main: `492f0e3`. Development, independent
audit and architect acceptance passed on 2026-11-15; see the
[verification record](browser-single-file-upload-acceptance.md). The authorized
submission follows task-branch review, green PR checks, merge, green main
checks and branch cleanup. Publication evidence is retained in the PR history.

## Purpose and non-goals

Select one fixed file in a page, separately click Submit, observe the actual
upload, and read the saved resource. Reuse the existing fixed-file API assets,
response/UI vocabulary, format 1, one-level inclusion and ordered Flow. No
private integration or product modifications. This is not proof of universal
browser compatibility, media rendering, storage durability or adoption value.

Support one unique visible enabled main-document file input, frozen memory
bytes, and a separate ordinary click causing finite same-page fetch/asynchronous
XHR multipart submission. No native chooser dialog, hidden-input proxy,
drag/drop, directory, multiple-file request, automatic upload on selection,
navigation submission, chunking, streaming, retry or media transformation.
R1 review: immutable input and observed-byte comparison introduce no expression
or transformation. Transport decoding observes values; it does not rewrite
the declared file or alter the application's submitted request.

## Approved expression

```yaml
schema_version: 1
scenario: documents.browser_upload_and_read
users: [editor]
parameters:
  title: Example attachment
steps:
  - id: open_upload_page
    do: open
    target: documents.upload_page
  - id: fill_title
    do: fill
    target: documents.title_input
    value: {from_parameter: title}
  - id: choose_attachment
    on_failure: stop
    do: select_file
    target: documents.attachment_input
    file:
      path: fixtures/sample.txt
      sha256: bd8d03cbbbd4c28fc0d0169b48ad89d0a9575a3e432bb70c8aa49c0b1cf9af36
    expect:
      ui:
        - {check: objects_matching_count, anchor: documents.selected_files, field: filename, value: sample.txt, count: 1}
  - id: submit_attachment
    on_failure: stop
    do: click
    target: documents.upload_button
    expect:
      request:
        method: POST
        path: [documents]
        body:
          title: {from_parameter: title}
        files:
          attachment:
            path: fixtures/sample.txt
            sha256: bd8d03cbbbd4c28fc0d0169b48ad89d0a9575a3e432bb70c8aa49c0b1cf9af36
      response:
        - {check: status_equals, value: 201}
        - {check: has, field: id}
      ui:
        - {check: objects_matching_count, anchor: documents.uploaded_files, field: filename, value: sample.txt, count: 1}
  - id: read_saved_document
    do:
      request:
        method: GET
        path: [documents, {from_step: submit_attachment, response_field: id}]
    expect:
      response:
        - {check: status_equals, value: 200}
        - {check: field_equals, field: title, value: {from_parameter: title}}
        - {check: field_equals, field: filename, value: sample.txt}
        - {check: field_equals, field: content, value: "sample document\n"}
```

The asset is the 16 ASCII bytes shown by the final content check. Selection
input and submitted-file obligation are deliberately separate declarations.
No implicit data transfer is inferred from the previous selection. A click's
explicit files also supplies the complete projected backend request.

`file` is required only on `select_file`, exactly a literal path/sha256 descriptor.
Selection accepts target, normal user/session and stopping fields, and optional
UI expectations; no value, key, object_id, request/response/backend_state,
polling or duration. It is one action, never an implicit Submit click.
`expect.request.files` is limited to click in this slice, with the same single
field descriptor and flat string body rules as explicit API files. All other
previously accepted forms keep their meaning. Unsafe/missing/changed/over-limit
assets fail before execution. Include and Flow preserve declaring directories
and share the loaded asset budget; expansion shows descriptors, never bytes.

## Feasibility evidence and permitted mechanism

Pre-implementation probes passed on Playwright 1.62.0 / Chromium 151.0.7922.34:
16 complete browser-level Fetch multipart captures equalled independently
received server bytes, covering text, binary NUL/high bytes, empty input,
FormData(form), appended files, fetch/XHR and file replacement/truncation.
Twelve production-instrumentation association cases passed for direct/awaited
trusted clicks and background, synthetic, selection-change and old-action
controls. Eighteen associated/diagnostic bodies matched server bytes. Exact
10 MiB and 10 MiB + 1 captures were independently checked against actual receipt.
These are feasibility results, not completed core or product acceptance.

The permitted source is browser-level Fetch.requestPaused.request.postDataEntries
paired through the existing native initiator nonce and Network request identity.
Require a nonempty bounded list and a strict base64 bytes member in EVERY entry.
Concatenate only those observed bytes. An empty encoded segment is valid;
a missing segment is not. Do not use selected input, fixture, expectation,
RequestSpec or source path to fill an observation gap. Do not fall back to
postData text, Playwright post_data_buffer or a JavaScript body wrapper.

The buffer route matters: disk-backed input experiments omitted file segments,
even for an empty file. Selection therefore uses the already frozen bytes and
does not reopen paths. Missing entries fail on every supported platform.
Chromium and protocol variability is a runtime evidence boundary, not a promise
about all browsers or versions. Selection generates input/change events, but
measured events are untrusted; no native chooser or trusted selection claim.

Preserve trusted click/native-await ownership and response pairing. Background
and selection-triggered traffic cannot satisfy the later click. Automatic
upload during selection is unsupported and must not silently consume a click
fixture, reach live API traffic in mock mode or become evidence for another
step. No marker headers, request replay, alternate HTTP client or target changes.

## Core and browser contracts

Add action-only optional `UiActionPermit.file: UploadFile`, bound into its
signature, plus explicit driver opt-ins `supports_file_selection(mode)` and
`supports_file_requests(mode)`, both false by default. Preflight unsupported
capability before authentication/context/earlier actions. Keep API driver opt-in
separate: browser uploads must never be silently executed through ApiDriver.

Add frozen keyword-only `UiFileSelection(target_matches, file)` and optional
`file_selection` on evidence and StepResult. Require strict integer one and an
actual valid UploadFile matching the permitted filename/bytes/digest. Pin and
recheck the same connected input, unique target, type, visibility/enabled state
and one actual selected file after selection. No first-match guessing, hidden
focus/click/style repair, tolerated skip or replacement target. Other actions
must not claim this receipt. Keep bytes/name out of default repr and diagnostics.
The helper derives File.type from the standard filename-extension MIME table,
independent of host MIME files, falling back to application/octet-stream for
unknown extensions. This does not inspect or transform content. Browser-ambiguous
double-quote/encoded quote or line-break filenames are rejected before UI execution;
the existing API filename contract remains unchanged.

The native parser derives text fields and files from complete captured multipart
and actual Content-Type only. Enforce complete framing and unambiguous part
headers/names, strict text decoding, bounded part/segment counts and no duplicate
fields, nested multipart or transfer encoding. A complete body with no file uses
files=None; an empty-content file remains a real UploadFile(data=b''). Compute
the observed digest independently. Pair copies through Recorder and normalization.
The browser's empty unselected-input placeholder (empty filename and zero
content) is no file, not a named empty file or unavailable capture. An empty
filename with nonempty content is unsupported evidence and errors.

BrowserSupport accepts host-side FileConfig, defaulting to existing file limits.
Bound raw multipart to max_file_bytes + 64 KiB, non-file overhead to 64 KiB,
parts to 32 and segments to 128; check encoded sizes before decoding and exact
decoded sizes afterwards. These bound helper decoding/retention, not Chromium's
earlier allocation of protocol events. Preserve action deadlines, diagnostic
budgets and complete owned cleanup. Do not expose file content in safe errors.

## Projections and outcomes

Backend skips requestless selection with unchecked UI obligations and sends
the click's explicitly declared request/files through its opted-in API driver.
Contract reuses backend recordings and cannot prove page selection or wire
receipt. Pure selection is EMPTY for backend/contract, not PASSED. Existing
aggregation and continuation semantics do not change.

Frontend uses explicit mock fixtures and actual browser request evidence, never
live fallback; it does not establish server persistence. Its existing refusal
of explicit API steps remains. Live e2e is the complete example's primary gate.
The shared UI loop remains the sole UI orchestration loop; same user/session
and retained Flow context rules remain. No automatic selection of projections.

Well-formed observed wrong file content/name/field, or complete missing file,
fails the declared request check (FAILED). Wrong saved content is FAILED.
Unavailable/ambiguous selection, incomplete/malformed capture, attribution
failure, evidence mutation or exceeded limits is ERROR with existing blocking.
Missing runtime dependencies remain BLOCKED. No comparison may promote missing
evidence to a pass. Errors cannot roll back already produced product effects.

## Acceptance matrix

1. Loader/expansion/review: exact approved syntax, wrong placement/types,
   required file/target, assets/pins/budgets, include/Flow origins, no extra depth.
2. Core: strict opt-ins and receipts, zero-effect preflight, signature mutation,
   stale/cross-user evidence, safe repr, no expectation leakage, owned copies,
   missing/wrong observed files and backend/contract/requestless outcomes.
3. Browser: actual frozen buffer selection, unique/missing/duplicate/hidden/
   disabled/replaced inputs, wrong selected bytes, actual fetch and XHR, direct/
   awaited clicks, stale/synthetic/background requests and selection auto-upload.
4. Raw evidence: binary/empty/text/PNG/PDF, wrong/name/field/content/drop controls,
   missing native slots (including disk-backed empty files), malformed base64 or
   multipart, exact/over limits, context cleanup and mock no-forwarding.
5. Two neutral consumers with different page/request mappings and actual server
   multipart parsing/storage/readback. Wrong bytes and false 201 cannot pass.
   Test complete live e2e, bounded frontend mocks and explicit backend/contract
   semantics without claiming their evidence is independent or equivalent.
6. Independent mechanism/core and consumer audits, focused tests, full guarded
   suite with actual Chromium, fresh dev-only Python 3.11/3.12, litmus, lock,
   hygiene and diff checks. No new dependency, CI platform, assertion vocabulary,
   private source or unrelated refactor. Record commands, actual failures/fixes,
   a short maintainer summary and remaining limitations before submission.
