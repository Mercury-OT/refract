# Exact HTTP response status assertions

## Authority and scope

The maintainer authorized sequential specification, development, independent
audit, and local acceptance of the next bounded capability on 2026-10-17.
The candidate YAML must be shown to the maintainer with an explanation after
local verification and before submission. This is not submission authorization:
do not stage, commit, push, create a PR, or merge in this task.

The starting public main is `67ce17f8855f976d138ee84e34e2df5fdde31cbe`.
Sources are the public response/recording models, public reference applications,
and the explicitly authorized product-neutral requirement to check HTTP status.
No private workspace, product, measurements, or evidence is needed or accessed.
Public documentation and examples remain English. MANIFESTO and BRAND are outside
scope. This specification describes a candidate until local acceptance and the
maintainer's YAML review; implemented language documentation must track the code.

## 1. Purpose and non-claims

Allow a response expectation to require one exact HTTP status or membership in
an explicit finite set. Examples are creation returning 201, deletion returning
204, and a caller deliberately accepting either of two documented statuses.
Do not require normalizers to expose a synthetic status field.

Status is an observed transport fact, not a rejection mechanism, authorization
proof, or proof of complete business acceptance. Existing normalized `success`
and `failure` keep their meaning. No multi-user execution, fail-continue change,
query/header/body extension, plugin system, or generic conformance framework is
included. A small normalizer-independence sample suite is part of acceptance,
not a claim that all adapters have been certified.

## 2. Candidate expression and declaration rules

Keep `schema_version: 1` and the approved `steps` / `do` / `expect` structure.
Add only these response checks:

```yaml
- check: status_equals
  value: 201
```

```yaml
- check: status_in
  values: [200, 204]
```

- `value` is a literal integer in the inclusive range 100 through 599.
- `values` is a nonempty list of distinct literal integers in that same range.
  Authored order is retained for review; membership is order-independent.
- Reject booleans, floats, strings, null, mappings, nested lists, references,
  missing/extra parameters, empty lists, duplicates, and out-of-range numbers.
  Neither form introduces a new reference position or runtime expectation.
- At most one HTTP-status check is allowed per step: reject repeated checks and
  simultaneous `status_equals` / `status_in`, even if their sets overlap.
- Checks belong only to `expect.response` on a request-bearing step. Existing
  effective-assertion and projection capability rules remain unchanged.
- Either check may coexist with normalized `success` or `failure`, field checks,
  collection checks, and state checks. Do not infer normalized success from an
  HTTP status class or reject combinations based on such an inference.

Existing declarations are unchanged. Adding these two checks does not change
the default fail-fast rule, polling budgets, users, include depth, or schema
version. Later changes to those semantics require their own specification.

## 3. Evidence and evaluation

Evaluate against the selected `RecordedResponse.status` captured at the response
boundary, before invoking the normalizer. Do not read the expected transport fact
from `NormalizedResponse.status`, `NormalizedResponse.raw.status`, or normalized
fields. A normalizer changing its input copy, replacing `raw`, or returning a
different status cannot turn the wrong recorded status into a passing check.

Pass the protected observed status explicitly through the common response
evaluation path. A new check without captured status must fail visibly; there is
no fallback to normalized status. Invalid observed status has a safe diagnostic
without echoing its value. For direct execution it is an execution ERROR and
retains existing subsequent BLOCKED behavior. Contract must also reject invalid
or missing status evidence when required, without producing PASS or exposing an
arbitrary malformed value.

Use the same meaning for backend requests, explicit e2e API actions, associated
live UI responses, and frontend mock responses. Mock observations remain mock
evidence, never provider evidence. Do not change UI request association rules or
repair missing traffic with an additional request.

For polling, evaluate the captured status on each actual attempt together with
the existing response predicate. Final checks must use the winning response;
FAIL timeout checks use the last attempt. SKIP timeout stays SKIPPED. Only the
existing final recordings contribute to contract; this task does not change
timeout response availability or the stopping predicate architecture.

## 4. Contract, inclusion, reports, and privacy

Consumer contracts retain the exact allowed HTTP status set independently of
normalized success/failure. Provider contracts retain status from the original
recording before normalization; normalize an independent copy so classification
cannot rewrite status or recording identity. Add any model fields as defaulted
keyword-only fields, preserving current construction. Do not change endpoint
identity `(step_id, method, template_path)`.

Missing, malformed, or nonmatching provider status cannot satisfy a declared
status requirement. A step without a status requirement retains its previous
contract behavior. The contract projection passes the keys requiring HTTP status
to provider extraction. Missing or malformed status at those keys produces
unavailable evidence without invoking the normalizer; unrelated keys retain
their existing normalization path. Reports name the status check and expected/observed valid
integer statuses; no new diagnostic prints response bodies, headers, raw objects,
session details, or normalized field values. Preserve existing sensitive repr
boundaries; do not introduce a serializer or promise universal redaction.

One-level inclusion and named results stay unchanged. Expanded child status
checks must be enforced, appear in explicit expansion, and appear as structural
changes in impact inspection. No runtime status-result reference is introduced.
Existing current-run response-field results continue to work alongside the checks.

## 5. Required acceptance evidence

1. Vocabulary and strict loader positive/negative tests, including 100 and 599,
   99/600, true/false, floating/string forms, invalid lists, duplicate checks,
   wrong observation points, references, and unknown/missing parameters.
2. Exact and set checks pass/fail independently of normalized success. Same
   normalized rejection with actual 400, 403, 404, or 500 is distinguishable.
3. A normalizer can change returned status, mutate its input status, replace
   `raw`, or expose a misleading status field: none changes the captured fact.
   Cover passing and failing neighbors, not only one mutation direction.
4. Actual invalid status is visible and cannot pass through Python coercion;
   new errors and mismatch details do not expose sensitive sentinels.
5. Backend and explicit e2e API paths exercise failure/blocking and recordings;
   frontend mock and live UI paths exercise the same status checks. Real Demo
   Chromium tests must run, not be replaced by only fake ports or skipped tests.
6. Polling covers successive different statuses, successful final selection,
   FAIL and SKIP timeouts, exact attempt records, and contract final-only use.
7. Contract preserves exact/set requirements, leaves old unconstrained shapes
   working, rejects missing/wrong/invalid status, and protects source recordings
   and identity from a mutating normalizer. No extra request is sent by contract.
8. Included child checks execute with qualified source identity. Validation,
   expansion, and impact inspection include new check fields without leaking
   runtime values or adding reference syntax.
9. Add a complete, executable neutral example. Demonstrate 201 creation and
   empty 204 deletion using the public Documents adapter, plus a fixed wrong-
   status counterexample with unchanged body/normalized success. Demo supplies
   an independent execution consumer and real browser evidence. Do not modify
   reference product behavior merely to make a check pass.
10. Public response documentation explains exact status versus normalized
    success and rejection cause. Correct the misleading assertion that generic
    `failure` proves a complete rejection mechanism. Full new YAML examples are
    tested through the real loader; fragments state their context.

Focused new-feature tests must demonstrate rejection on the baseline and pass
after implementation. Reuse existing tests and passing neighbors; do not build
a generic mutation or adapter-certification platform. Independent audit includes
counterexamples beyond the developer's happy-path fixtures and source review.

Run the complete suite with real browser tests, an isolated dev-only core suite,
maintained Scenario validation, `uv lock --check`, repository hygiene, and
unstaged/cached diff checks. Record actual results and scope without inferring
real-product migration, security assurance, or human-effort savings.

## 6. Delivery and stop point

Expected files are this specification, a local acceptance record, the roadmap,
SCENARIO response/contract guidance, vocabulary/loader, response evaluation and
its existing UI call site, contract models/diff, focused tests, and neutral public
examples. A small shared pure helper is allowed if it avoids divergent status
rules. No dependencies, CI filters, authentication, ports, report state model,
browser instrumentation, private material, or unrelated historical edits.

Architect acceptance follows independent audit. Stop with all changes unstaged
and uncommitted. Explain the new capability in plain language and show one
commented typical YAML example to the maintainer. Their subsequent review and
separate submission authorization are required before publication.
