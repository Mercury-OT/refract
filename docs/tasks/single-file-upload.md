# Fixed single-file API uploads

Status: expression, binary-file scope, implementation, independent review and
post-acceptance submission authorized by the maintainer on 2026-11-10.
Starting main: `18d9b2e`. Publication remains conditional on architect acceptance,
green PR checks, and green post-merge main checks.
Development, independent audits and architect acceptance passed on 2026-11-11;
see the [verification record](single-file-upload-acceptance.md). Publication is
recorded separately by the associated task PR and main history.

## Purpose and boundaries

Upload a reviewed local file unchanged and read the resulting resource through
the existing response assertions. Text, images, PDF and small video files are
byte inputs, not different declaration types. This does not verify image
rendering, PDF preview, video playback, import semantics or arbitrary storage
durability. Product-specific routing, credentials and media-type configuration
belong to adapters; expectations never enter an action port.

Keep `schema_version: 1`, the overall Scenario structure, one-level inclusion,
ordered Flow, existing assertion vocabulary and result states. No workroom or
private-product access. Public sources and synthetic examples only.

R1 review: the file is immutable input data. Computing a fingerprint verifies
identity; it does not transform a declared value. No expressions, dynamic paths,
file generation, string conversion, media transcoding or new control flow.

## Approved expression

Only an explicit `do.request` may add `files`, a nonempty mapping with exactly
one literal upload field. Its descriptor has exactly `path` and `sha256`, both
literal strings. The SHA-256 is exactly 64 lowercase hexadecimal characters.

```yaml
schema_version: 1
scenario: documents.upload_and_read
users: [editor]
parameters:
  title: Example attachment
steps:
  - id: upload
    on_failure: stop
    do:
      request:
        method: POST
        path: [documents]
        body:
          title: {from_parameter: title}
        files:
          attachment:
            path: fixtures/sample.txt
            sha256: bd8d03cbbbd4c28fc0d0169b48ad89d0a9575a3e432bb70c8aa49c0b1cf9af36
    expect:
      response:
        - {check: status_equals, value: 201}
        - {check: has, field: id}
  - id: read
    do:
      request:
        method: GET
        path: [documents, {from_step: upload, response_field: id}]
    expect:
      response:
        - {check: status_equals, value: 200}
        - {check: field_equals, field: id, value: {from_step: upload, response_field: id}}
        - {check: field_equals, field: filename, value: sample.txt}
        - {check: field_equals, field: content, value: "sample document\n"}
```

The fixture is the 16 ASCII bytes `sample document` followed by LF. The normal
request body remains separate from file bytes. For upload requests, any body is
a flat mapping of text fields, including ordinary existing references resolving
to strings. No implicit conversion of numbers, booleans, null, objects or lists;
no overlap between text-field and file-field names. The file field is a literal
HTTP token; the filename is the asset's basename, not an adapter invention.
No `Content-Type`, MIME selector, encoding field or filename override is added
to YAML. The public sender demonstrates ordinary multipart; exact transport
format is not a new declaration assertion.

No `expect.request.files`, UI file selection, multipart browser interception,
multi-file request, directory, remote URL, dynamically selected file, download,
chunking, resumable transfer or streaming is included. Existing GET polling
cannot repeat an upload. Object-state checks and waiting retain their existing
single-action rules.

## Asset identity, budgets and ownership

Paths are relative to the Scenario which declares the file, including a child
loaded through include or Flow. They must be literal contained regular files:
no absolute paths, parent traversal, glob, URL, symlink or device/FIFO. All assets
are checked and read before execution-side effects, and the bytes are frozen
for that loaded execution. Never reopen a filename at send time. A later load
rechecks the fingerprint; replacing a loaded file cannot replace its snapshot.
Dependency pins retain the declaring Scenario's file descriptor and therefore
its expected content identity. Hashes prove identity, not human approval.

A host-side file budget is configurable outside YAML: default 10 MiB per file
and 64 MiB total frozen assets per loaded Scenario/Flow. Limits are strict
positive integers (not booleans); exactly-at-limit succeeds, above-limit fails.
Do not load unbounded content before checking limits. The total applies across
the composition, not independently to each child. Count distinct source assets
once when snapshots are reused, and document that identity explicitly.
Empty files remain valid inputs so the product can accept or reject them.
The initial reader uses POSIX directory-relative, no-follow file descriptors;
hosts without those safe-open facilities reject uploads explicitly. This is
not a new portability claim for upload execution on untested platforms.

RequestAction and RequestSpec receive an owned file mapping carrying immutable
bytes, filename and verified digest. They never receive an expectation, source
declaration, absolute local path or file-reading callback. Resolver changes,
omissions or additions are errors. An API driver explicitly opts into file
support; legacy drivers cannot silently ignore it. Capability and known-invalid
assets fail before authentication or an earlier business action. Runtime text
references of the wrong type block before sending that step.

Preserve frozen assets through parameter binding, include expansion, Flow source
loading, contract replay, review comparison and CLI expansion. Expansion shows
the declared descriptor, never raw bytes or absolute paths. Sensitive values,
file bytes and filenames stay out of default repr and sanitized exceptions.

## Execution and evidence

Backend and explicit API actions in live e2e reuse the same sender path. An API
action inside e2e is not browser upload evidence. Frontend keeps its existing
rejection of explicit API actions. Contract uses recordings; it does not upload
again or independently observe the wire or storage. Old file-free requests stay
compatible and never require file capability.

The cooperative adapter boundary is unchanged: core validates data ownership
and request/response pairing, not the honesty of arbitrary in-process code.
Echoing an intended digest in a recording cannot prove bytes reached a server.
The public consumers must independently parse actual incoming multipart bytes
and read actual saved bytes on a later request. File dropping, truncation and
substitution must fail these controls even when a driver echoes the expected
request metadata. Ordinary product mismatches are FAILED; unavailable or
malformed evidence/capability is ERROR, and missing runtime dependencies are
BLOCKED. No new status or auto-retry. A 201 alone never proves persistence.

## Implementation and acceptance matrix

1. Loader: complete syntax, empty/multiple/unknown keys, wrong hash/path types,
   dynamic references, unsafe paths, symlink/regular-file checks, mismatched
   hashes, exact/over budgets, and valid empty/binary inputs. Reject UI files
   before any resource is opened. All negative examples use synthetic assets.
2. Runtime: explicit capability, zero-effect preflight, filename/content/digest
   ownership, malicious nested mutation, missing/wrong text references, safe
   repr/errors, immutable snapshots and accurate recording/contract checks.
3. Composition: child's directory wins over same-named parent asset; pins and
   changed contents fail; reused child and Flow use frozen assets; review and
   expansion preserve descriptors; total budget spans dependencies.
4. Real consumers: one Documents upload/read API and an unrelated Records
   attachment API, different field/path mappings, actual multipart parsing,
   saved-file reads, text/PNG/PDF/non-text bytes and empty-file controls. Verify
   received bytes, not only names/digests supplied by the client. Wrong bytes,
   missing fields and false successful responses cannot produce false passes.
5. Mechanical gates: focused tests, independent adversarial audit, full guarded
   suite with real browser regression, dev-only Python 3.11/3.12, litmus,
   documentation/expansion sentinels, lock, hygiene and diff checks. Core has no
   HTTP/browser/product dependency. Prefer existing libraries; no new dependency
   or CI expansion without a demonstrated need within this scope.

The developer and independent reviewer must record actual commands/results.
Acceptance includes a short maintainer summary and the evidence limits above;
passing synthetic consumers is not measured real-product adoption value.
