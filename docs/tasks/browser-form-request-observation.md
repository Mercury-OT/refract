# Browser observation of ordinary form requests

## Authorization and scope

The maintainer approved this bounded direction on 2026-10-25 after clarifying
that request encoding normally belongs to the adapter, not Scenario authoring.
Specification, development, independent audit and local architect acceptance
are authorized. Submission requires a separate instruction. Starting main is
`f155ad50acd3d3d2c42ae3963a48e80690d63ac4`.

Keep schema version 1, existing YAML, one-level inclusion, ports, core, assertion
vocabulary and execution semantics unchanged. Do not modify private workspaces,
products, dependencies, CI, MANIFESTO or BRAND. Sources are the approved neutral
requirements, public code and independently authored synthetic browser fixtures.
All public text and examples remain English. Do not add product-specific names,
paths, samples or encoding rules.

## Purpose and non-claims

Let the existing optional BrowserSupport collect ordinary UTF-8
`application/x-www-form-urlencoded` fetch/XHR requests alongside JSON requests.
Scenario continues to describe business fields; it does not acquire an encoding
selector or media-type assertion. A product ApiDriver can already choose JSON
or form encoding per endpoint. This task does not create that capability or
claim that core independently checks an ApiDriver's network bytes.

Verify actual browser input and real server receipt without obtaining body
values, types or formats from expectations. Existing response checks decide
success. Mock evidence stays mock evidence; contract reuses recordings and is
not an independent observer of request encoding. The task establishes support
on a synthetic consumer, not production adoption or measured review savings.

## Observation contract

1. Select form decoding from the actual observed Content-Type header, with
   case-insensitive media type. Accept exactly
   `application/x-www-form-urlencoded`, optionally followed by a single
   `charset=utf-8` parameter (case-insensitive, optionally quoted, optional
   surrounding whitespace). Other parameters/charsets, repeated charset and
   ambiguous form Content-Type declarations fail visibly. Check the full header
   pair list, including duplicate rows and comma-combined ambiguous values.
2. Use actual request bytes for the form branch, with strict UTF-8 decoding.
   Split field pairs before decoding; decode percent escapes and plus-as-space
   once. Reuse the existing strict query decoder where its behavior is identical.
   Malformed escapes, invalid UTF-8, empty decoded names and repeated decoded
   names fail rather than being replaced, coerced or silently overwritten.
3. The resulting body is a flat string-to-string mapping. Preserve empty values,
   `"0"`, `"false"`, `"null"`, Unicode and literal special characters. A bare
   nonempty key has an empty value; empty separators carry no field. Dots and
   brackets in a name remain literal characters, never nested structures.
   Repeated values, arrays and product-specific nested-form conventions are not
   inferred. The unchanged strict body check distinguishes strings from numeric,
   boolean, null, list or object expectations.
4. When actual bytes are available, an empty byte string decodes to an empty
   mapping. If the browser provides no body, retain None; do not reconstruct
   an empty form from expectations or claim the browser preserved a distinction
   it did not expose. Record real-browser behavior in acceptance.
5. Outside the form branch, retain the existing JSON-object/null decoding
   behavior, including existing handling of missing/non-form Content-Type.
   This is not a new general HTTP media-type validator or a JSON-parser
   hardening task. A form-looking body with no form header is not guessed to be
   a form. A malformed form claim cannot fall back to JSON.
6. Decode before forwarding a live request or consuming a mock fixture. Errors
   use the existing sanitized browser failure path, without raw body, key,
   value or header contents in human-readable error/report repr. Preserve raw
   observed header pairs as sensitive evidence. Do not add a body-byte field
   to a core port or claim existing reports retain exact wire bytes.
7. Forward live requests without changing their body or Content-Type. Preserve
   action/request/user/session association, response pairing, trace rules,
   background diagnostics and ordered mock consumption. A matching unassigned
   request cannot substitute for an action's missing request. Mock responses
   remain independently authored; no new fixture body-matching API is added.

The form field splitting and decoding follow the WHATWG URL Standard's
application/x-www-form-urlencoded parsing model (section 5.1).
The strict malformed-input and duplicate-name rejection above is a bounded
evidence policy, not a claim to accept every form a browser or server accepts.

## Unchanged limits

Only the already supported same-origin fetch and asynchronous XHR paths gain
form observation. Native HTML form navigation, multipart/files, arbitrary raw
bodies, streaming, unsupported asynchronous origins, cross-origin requests and
redirects remain outside the helper's supported scope. No encoding registry,
arbitrary decoding callback, automatic retry, new action or new YAML field.
Unknown evidence cannot be repaired using Scenario expectations or an extra
API request. Core and all existing Scenario files remain byte-for-byte unchanged.

## Implementation and public guidance

Use a small private helper in `refracto_browser` if that makes decoding separately
testable. Keep Playwright optional and lazily imported. Add offline decoder tests
and real Chromium tests using a neutral page/server that sends both JSON and
form requests. An executable existing-format YAML example must be loaded and
run by tests; its body expectations contain business strings, not encoding
instructions. Guide readers to endpoint-specific ApiDriver serialization and
truthful browser decoding, without asserting that all form integrations were
previously impossible. Clarify native form navigation versus fetch/XHR bodies.

## Acceptance matrix

- Actual fetch and XHR, live and mock: ordinary forms, special characters,
  Unicode, empty values, bare names, one-time decoding, string type preservation.
- One loaded multi-step Scenario handles JSON and form in the same application;
  final RunReport is PASSED without degradation in each selected projection.
  Real server receipt verifies body bytes and Content-Type; mock mode performs
  no API forwarding and preserves independent fixture identities.
- Wrong/missing business fields and string-versus-number/bool mismatches cannot
  pass the existing request check. Plain assertion failures retain current
  continuation behavior; decoding errors use current ERROR/blocking semantics.
- Repeated names, including differently encoded aliases, malformed percent
  escapes, invalid UTF-8 bytes, unsupported/duplicate charset and ambiguous
  form Content-Type fail before server receipt or fixture consumption.
- Form syntax is not inferred without a form header. JSON behavior remains
  unchanged. Empty/absent body behavior is verified, not invented.
- Background form requests stay diagnostic; same-path repetitions retain
  separate identities. Evidence tampering remains rejected. Unsupported native
  form writes still fail without forwarding. Sensitive values do not appear in
  new errors or final report repr.
- Offline tests run without browser packages; real Chromium tests run without
  skips in the full environment. Full regression, core-only checks, import
  litmus, lock consistency, repository hygiene and diff/index checks pass.
- Review changed/untracked sources for neutrality. Verify no core, existing
  Scenario, dependency, CI, MANIFESTO or BRAND changes and an empty index.

Deliver this specification, implementation, tests, executable neutral example,
updated browser guidance and priority index, and a local acceptance record with
actual commands, results, limitations and independent audit findings. Do not
stage, commit, push or create a PR as part of this task.
