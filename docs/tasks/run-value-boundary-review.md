# Run-value boundary review and diagnostic corrections

Historical status: bounded corrections passed independent audit and architect
acceptance on 2026-10-26 under the maintainer's defect-correction authorization.
Starting main: `85bb13d`. At that checkpoint, isolation and literal-rule proposals
were unimplemented. This acceptance did not authorize submission.

Subsequent authorization, 2026-10-26: after reviewing concrete examples, the
maintainer approved [scoped unique values and explicit literal parameters](scoped-unique-values-literal-parameters.md).
That new task changes the semantics deliberately. The observations, test counts
and acceptance below describe the earlier diagnostic-only state; they are not
claims that the collision behavior must remain in the new implementation.

## Scope and sources

Use the public implementation, its approved contracts, Git history and synthetic
Records/Documents consumers. No private workspace or product material is used.
Keep format 1, one-level inclusion, assertion vocabulary, ports and current
run-value semantics. This is not authorization for Flow or new time formats.

## Confirmed correction

The loader currently replaces an out-of-range time-offset diagnostic with a
generic parameter-dependency/concat error. Extract direct parameter parsing into
a small helper, validate typed time offsets there, and retain the specific,
value-free reason as a DeclarationError. Preserve all valid declarations and the
literal-data boundary. Do not expose supplied values in diagnostics.

Clarify the existing runtime preparation-error contract in SCENARIO.md:
ValueError occurs before projection execution and no RunReport is returned.
This documents current behavior; it does not introduce report conversion.

Update the current status at the top of the unique/concat and relative-time
specifications to reflect their merged commits. Preserve historical acceptance
and authorization records. Record the completed browser-form delivery in the
roadmap using verified Git history.

## Observations and unresolved choices

- One token is shared across all projections and included instances in a logical
  run. Multiple real writers against the same target can collide; a shared
  token is not a distinct-object identifier for each invocation.
- Separate runner calls generate separate tokens. A future path composition
  mechanism must define its run boundary; no implemented Flow behavior is claimed.
- Multiple direct unique parameters intentionally receive the same token.
- Ordinary parameter dictionaries retain marker-looking data literally, as
  explicitly approved. A reference-shaped dictionary is not a parameter alias.
- Valid offsets that overflow a selected runtime base fail before ports with
  ValueError. Existing tests specify this configuration/preparation boundary;
  converting it to a RunReport is a separate design choice.
- Date-only/epoch/timezone values, time-order assertions and token-length controls
  are unsupported capabilities, not corrections authorized by this task.
- Current hosted CI runs pytest sequentially. Oversubscribed browser execution
  is not evidence of a failure of that configured execution model.

The maintainer requested concrete proposals for automatic value isolation and
stricter parameter-literal rules before either is implemented. Do not add warning
behavior, derive new tokens, reject previously legal dictionaries, add an escape
syntax, or implement new time formats in this correction. Collision tests record
the present limitation; they do not establish that it has been removed.

## Validation and acceptance

1. Require precise diagnostics for both signs and all supported offset units at
   the representable-range boundary, without echoing parameter values or names.
2. Retain valid boundary neighbors, strict integer checks, dependency/concat
   failures, symbolic loading and literal-dictionary behavior.
3. Independently verify shared-target collisions and separate-run controls with
   synthetic storage; report the actual evidence without treating every green
   echo test as proof of uniqueness isolation.
4. Run focused tests, the full sequential suite with Chromium, import-direction
   checks, lock, hygiene and Git diff/index checks after the final correction.
5. Independent audit and architect acceptance precede any separate submission
   instruction. Keep all changes unstaged. Do not access the private workroom.

## Local acceptance, 2026-10-26

The only runtime-code change is parameter-parser extraction and preservation of
the specific offset-range diagnostic. The unique generator, run binding, runner,
report models, assertion vocabulary, dependencies and CI configuration are
unchanged. SCENARIO.md documents the existing preparation-error behavior.

| Check | Observed result |
| --- | --- |
| New offset diagnostics and boundary tests | Before correction: 8 failed, 16 passed; after correction: 24 passed |
| New shared-storage scope/control tests | 6 passed; collisions remain visible failures |
| Independent focused audit | 220 passed |
| Independent baseline/current parser comparison | 44 valid/invalid forms agreed outside the intended diagnostic change |
| `uv run pytest -o addopts='' -q` | 4194 passed, no skips, one existing dependency warning; real Chromium executed sequentially |
| Fresh Python 3.12 environment, editable `.[dev]` install, `python -m pytest -o addopts='' -q` | 3624 passed, 1 optional integration collection skip |
| Run-value/time and stabilization documentation tests | 48 passed |
| `uv run pytest tests/test_opensource_litmus.py -o addopts='' -q` | 3 passed |
| `refracto validate` on an excessive-offset synthetic declaration | Exit 2 with the specific range diagnostic |
| `uv lock --check`, repository hygiene and Git diff/index checks | Passed; index empty |

An initial ad-hoc command mistakenly invoked `python -m refracto.cli`, which is
not the registered command entry point and did not run validation. The probe was
corrected to the installed `refracto validate` entry point; no implementation
change was made for that probe error.

The new scope tests use an in-memory synthetic Records target with persistent
storage and fixed request handling. They are not browser/network evidence and do
not claim automatic isolation. Existing full-suite browser tests remain separate
evidence. Shared-target backend/e2e execution and repeated child defaults collide;
explicit distinct include inputs and separate runner calls pass their controls.

No blocking findings remain for this bounded correction. Automatic scope changes,
literal-rule tightening, new time representations, timestamp comparisons,
token-length selection and preparation-error reports remain separate decisions.
Parallel browser reliability under constrained resources was not measured here;
sequential success does not settle that question. No private workspace access,
staging, commit or publication was performed.
