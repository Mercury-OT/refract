# Run-unique values and bounded string composition

Status: specification and implementation authorized by the maintainer on
2026-10-22 after review of the expression below. Submission is not authorized.
Starting main: `14a7f88`. Format 1 and one-level pinned inclusion remain unchanged.

Delivery: [local acceptance](run-values-concat-acceptance.md) passed on 2026-10-22.
This specification and its acceptance do not authorize submission.

## Resumed verification authorization

On 2026-10-24 the maintainer reconfirmed the same annotated expression and
authorized verification of the preserved implementation, independent audit and
architect acceptance on main `ac71abf`. Reuse the existing implementation rather
than redeveloping it. Correct only demonstrated in-scope defects; do not expand
the language or task. Format 1 and one-level inclusion remain unchanged. No
private workspace access, staging, commit, push or publication is authorized.
The earlier acceptance remains historical. The
[resumed verification and acceptance](run-values-concat-acceptance.md#resumed-verification-2026-10-24)
passed without implementation changes; submission still requires a separate
maintainer instruction.

The maintainer subsequently accepted that result and authorized the separate
[public submission workflow](run-values-concat-acceptance.md#subsequent-submission-authorization-2026-10-24).
This does not expand the approved expression or implementation scope.

## Purpose and public sources

Avoid reusing static test identifiers between executions, and compose strings
from actual values without adapter-owned business transformations. This task
uses only the public contract, implementation and synthetic Records/Documents
examples. Private workspaces and products are not accessed or modified.
It does not prove adoption value, global collision impossibility, environment
isolation, automatic cleanup, or a general expression language.

## Approved expression

```yaml
parameters:
  run_token: {from_run: unique}
  document_title:
    concat:
      - {from_parameter: run_token}
      - "-document-"
      - {from_parameter: run_token}
```

In a later step's existing reference-capable value position:

```yaml
concat:
  - {from_step: account, response_field: account_code}
  - "-document-"
  - {from_step: batch, response_field: batch_code}
```

Only direct `parameters.<name>` values recognize `{from_run: unique}`.
The marker has exactly that key and literal name. No prefix, suffix, alternative
generator, time value or direct step-level `from_run` expression is accepted.
Direct parameter values may also declare `concat`; its operands are strings
or references to declared parameters. Ordinary parameter dictionaries, including
nested marker-like data, remain literal. A direct plain `from_parameter` mapping
outside concat retains the existing literal-data meaning.

`concat` has exactly one key and a nonempty list of operands. Operands are
literal strings or existing parameter/response references; response members and
named child results use the already approved reference forms. No nested concat,
arithmetic, templates, dynamic keys, loops, conditionals or implicit conversions.
Parameter dependencies may be forward declared but must be acyclic. Parameters
cannot reference responses. Resolved parameter values can feed another concat;
this is reuse of a value, not nested syntax or repeated generation.

The result is a string; empty string operands and an empty result are allowed
only where the existing destination permits them. Numeric-only assertion slots
and reference-only identity slots do not acquire new accepted types. Structured
body/query/header containers are not themselves string destinations. Literal
or known parameter type errors fail declaration validation; missing, null or
wrong-type response operands block the consumer before action, preserve the
existing dependency diagnostics, and cannot yield a default or a false pass.

## Run, composition and evidence boundaries

- Loading, validate, expansion and impact inspection are deterministic and do
  not generate tokens. Expanded views show symbolic declarations, never runtime
  values; the authoring expansion API rejects already-bound run models. Invalid
  declarations fail before authentication, browser or transport.
- A selected top-level `run_scenario` freezes one UUID4 hex token if the compiled
  declaration contains a run marker, including an unused declared parameter.
  All projections, polling attempts and included leaves use that token. A new
  invocation obtains a new token; it is not a server object ID or a secret.
  No token is needed for a filtered-out scenario or declarations not using it.
- Freeze on a fresh copy, preserving reusable declarations. Include substitutions
  must preserve parameter scope, caller overrides, response dependencies, pins,
  named results and user mappings. Overriding a child input must also affect its
  dependent concatenated defaults. No expansion of the inclusion depth.
- Parsed typed expressions, not dictionary-key recognition at runtime, drive
  evaluation. Literal parameters, adapter observations and values passed through
  include overrides must never become new executable declarations.
- Record the run token explicitly on RunReport with sensitive/default-repr
  protection; do not auto-serialize all resolved parameters. Retain existing
  sensitivity boundaries for bindings, requests, permits and report evidence.
- API, mock/live UI, e2e and contract use the same preparation/value rules.
  Contract replays the run's frozen inputs and actual provider responses, not a
  fresh token. Low-level projection entry points must not silently invent tokens
  for an unbound declaration; document explicit binding when used independently.
- Composition does not make invalid paths, query/header values or missing evidence
  valid. Keep per-segment URL encoding, strict comparison and continuation rules.

## Verification and delivery gates

1. Tests first: generation is absent from validation, exactly once per logical
   run, stable within run/projections/includes and fresh across runs. Exercise
   concurrent/repeated execution and no mutation of loaded declarations.
2. Reject unknown markers, extra keys (including prefix/suffix), malformed or
   nested concat, nonstring operands, missing/cyclic parameter references and
   response references in parameters. Test valid empty-string neighbors.
3. Verify direct response, selected member and named-result operands; malformed,
   missing, null, numeric, boolean and container values block before action.
   Preserve atomic bindings, independent continuation, provenance and privacy.
4. Include tests cover dependent defaults, caller parameter/response overrides,
   repeated child invocations and literal marker-looking data. No regenerated
   tokens, scope capture or incomplete binding dependencies are acceptable.
5. Run real synthetic Documents and independent Records create/query/read
   consumers. Exercise API/backend+contract and actual browser mock/live paths;
   selected faulty response/reference evidence must not pass contract.
6. Keep CLI expand/impact symbolic and JSON serializable. Update SCENARIO.md,
   roadmap, neutral examples and their executable documentation sentinels.
7. Full regression with Chromium, dev-only isolation, core import litmus, lock,
   hygiene and diff checks. Assertion vocabulary and frozen measurement artifacts
   stay unchanged. Independent audit then architect acceptance; no submission
   without a separate maintainer instruction.

All new public material is English and product-neutral. Relative time, runtime
parameter override APIs, multiple independent random generators, deeper include,
environment management and unrelated cleanup/refactoring remain out of scope.
Here "bounded" limits the available operations, not the maximum generated string
size. Parameter analysis avoids repeated traversal of shared dependencies, but
large composed outputs still require ordinary host memory. No new output-size
quota or general untrusted-input resource sandbox is claimed.
