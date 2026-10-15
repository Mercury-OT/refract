# Scenario inclusion: approved implementation specification

> Historical first include specification. The subsequent approved
> [named-results specification](scenario-named-results.md) replaces direct
> caller access to child step IDs with explicit `results` / `result` references.
> The original examples and acceptance record below describe that earlier
> interface, not a compatibility syntax supported by the named-results change.
> All unaffected one-level, same-actor, pinning, and execution boundaries remain.

## Authorization and delivery gate

The maintainer approved Stage B development, independent audit, and architect
acceptance, selecting identical parent/child actors and option B (parent sidecar
pins). This is implementation authorization, not an assertion of delivery or
submission authorization. The inspected baseline is public main
`9bebfa7559bfc22e7121bc31b1945e803676a1f8`. The executable language is documented
in [SCENARIO.md](../../SCENARIO.md); delivery status belongs in the
[roadmap](../roadmap.md).

Stage A produced this specification and its acceptance/negative-test plan.
The two selected decisions below close that stage's approval gate. Development,
independent audit, and architect acceptance follow in that order. Neither stage authorizes staging,
commits, pushes, pull requests, or merges. No private workspace, product source,
historical evidence, MANIFESTO, BRAND, or graphical workbench changes belong here.

Sources are the public implementation and the product-neutral requirements in
this proposal. Examples are synthetic. No private adapter, scenario, measurement,
or approval record is incorporated into this document.

## 1. Purpose and claims

Allow an ordered Scenario to include all steps of another reviewed, content-pinned
Scenario. Preparation becomes visible declared work executed in the current run,
instead of an implicit fixture assumption or an adapter's hidden business script.

Inclusion does not create checks, evidence channels, or independence. Actual
coverage depends on the declarations, selected projections, and adapter support.
Contract consumes backend recordings; it does not independently execute the
preparation. This task does not establish lower review cost, improved approval
quality, complete business acceptance, or real-product adoption.

This is restricted sequence composition. It introduces a small language extension
(`include`, `with`, and qualified references), not literally zero new syntax.
It adds no general functions, expressions, branching, recursion, or dynamic plan.
The approved one-primitive-per-step rule remains true of every executed leaf;
an include is explicitly a composition node, never an adapter primitive.

Content matching, human approval, and runtime success are separate claims:

- A SHA-256 match binds the exact child bytes. It does not prove who approved them.
- Approval uses the existing review process, covering the declaration and its
  intended uses. There is no self-authorizing `approved: true` field.
- An unchanged reviewed child need not have its internals repeatedly reviewed.
  The parent still requires review of purpose, actor, parameters, ordering,
  response references, and whole-flow obligations. Parameter values can change
  assertion expectations; they are not universally pre-approved.
- Every inclusion executes again. Prior PASSED results are never execution caches.

## 2. Approved expression

The following two files illustrate the approved Stage B language. They are not
claimed to be executable on the Stage A baseline. They use the selected
sidecar dependency option from section 3; the sidecar must also be supplied.

Child file, `shared/create_record.yaml`:

```yaml
schema_version: 1
scenario: demo.create_record
actor: editor
parameters:
  record_name: Example record
steps:
  - id: create
    do:
      request:
        method: POST
        path: [records]
        body:
          name: {from_parameter: record_name}
    expect:
      response:
        - check: success
        - check: has
          field: id
        - check: field_equals
          field: name
          value: {from_parameter: record_name}
```

Parent file, `create_read.yaml`:

```yaml
schema_version: 1
scenario: demo.create_read
actor: editor
parameters:
  record_name: Included record
steps:
  - id: setup
    do:
      include: demo.create_record
    with:
      record_name: {from_parameter: record_name}
  - id: read
    do:
      request:
        method: GET
        path: [records, {from_step: setup/create, response_field: id}]
    expect:
      response:
        - check: success
        - check: field_equals
          field: name
          value: {from_parameter: record_name}
```

Under the selected sidecar option, an include step accepts exactly `id`,
`do: {include: <literal Scenario ID>}`, and optional `with`. The include ID is
not a filename or an expression. `with` is a mapping of child parameter names
to existing declaration-value forms: finite JSON-like values, caller parameter
references, or earlier caller response references. Existing reference placement
rules still apply; no interpolation, arithmetic, or new reference form is added.

The caller may read an included request-bearing step with
`{from_step: setup/create, response_field: id}`. There are no exports, returns,
or output declarations. Consequently, the child's request-bearing step IDs are
part of its usable interface: renaming, removing, or changing one to a non-request
step can break callers. This is an explicit coupling tradeoff, not full encapsulation.

## 3. Dependency identity and fingerprint: option B selected

Option B is the approved implementation. Option A is retained below only to
explain the considered tradeoff; it must not be implemented in this task.

Both options require a literal Scenario ID, a local relative path, and a lowercase
64-hex SHA-256 of the complete child file bytes, before decoding or parsing.
Comments, whitespace, and line endings count. Any byte change requires an explicit
pin update and review of the change and affected uses; no auto-update or fallback.

| Option | Shape | Benefit | Cost |
| --- | --- | --- | --- |
| A: inline | `do` contains `include`, `path`, and `sha256`; `with` stays beside `do`. | Each call is self-contained. | Repeated calls repeat machine-oriented paths and hashes in the human-facing YAML. |
| B: parent sidecar, recommended | `<parent-stem>.includes.json` maps child Scenario IDs to `{path, sha256}`. YAML retains only `include` and `with`. | Small call sites and one pin per child per parent. | Review and distribution must include both the parent YAML and its sidecar. |

For option B, the JSON object has exactly `manifest_version: 1` and `scenarios`.
`scenarios` is a nonempty mapping from literal Scenario ID to an object with exactly
`path` and `sha256`, both nonempty strings with the constraints above. Duplicate
JSON keys, unknown fields, malformed hashes, and entries not referenced by this
parent are errors. Its key set must equal the parent's distinct include targets.
For `create_read.yaml` the sidecar is `create_read.includes.json`; it has one
`demo.create_record` entry pointing to `shared/create_record.yaml`, pinned to that
file's actual SHA-256. No placeholder hash is valid. A parent without include
does not consult a sidecar. There is no repository-wide registry or discovery scan.

For option A, each include's `do` has exactly the three fields in the table.
Repeated references to the same Scenario ID must have the same path and hash;
there is no sidecar and no simultaneous support for both options in this slice.

Common resolution rules:

- Paths are relative to the parent declaration's directory, independent of cwd.
  Use literal slash-separated paths inside that directory. Reject absolute paths,
  URI schemes, parent traversal components, backslashes, globs, and variable
  expansion. Do not percent-decode paths. Dependency path components must not be
  symlinks, and canonical resolution must remain within the allowed directory.
- The sidecar, if chosen, is a regular local file beside the parent, not a symlink.
  Missing sidecars, files, or entries are declaration errors. No network resolver,
  package search, alternate version, or environment-specific fallback is allowed.
- The mapped ID, include target, and child's declared `scenario` must agree.
  Two IDs must not alias one file. Self-inclusion and any child containing include
  are rejected before execution; cycles cannot be executed.
- Read each referenced file once per load. Hash, decode, validate, and expand the
  same immutable byte buffer. Repeated calls reuse these verified source bytes,
  never mutable compiled steps or prior execution results. A subsequent load
  rereads and rechecks the pin. Do not hash and then reopen to parse different bytes.
  The parent's source hash also uses the same byte buffer as its actual parse.
- All dependency checks complete before authentication, waits, request mapping,
  network calls, context creation, or UI actions, including errors in later calls.
- A composition load is bounded to 64 distinct child files and 1,000 expanded
  leaf steps, inclusive. Reject exceeding either bound before execution; do not
  truncate. These are conservative engineering bounds, not measured scale claims.
  Existing non-include declarations retain their existing limits.

This protects against accidental drift and inconsistent reads, not an attacker
who can rewrite both a declaration and its pin, replace the verifier, or control
the adapter. The task does not establish a hostile-filesystem sandbox or signed
approval infrastructure.

## 4. Expansion and value semantics

Load and validate the complete dependency set, then deterministically produce the
existing flat execution model. Do not recursively call `run_scenario(child)`.
There is one root projection selection and the existing execution loop, recorder,
session, and UI-context lifecycle for each selected projection.

1. A child must pass standalone declaration validation using its own defaults,
   including at least one effective assertion. Its references must be entirely
   self-contained. An assertion-free library Scenario is not introduced.
2. Source step IDs in a composition graph must not contain `/`; that separator is
   reserved for generated IDs. Ordinary non-composition files are not silently
   renamed. Each child leaf becomes `<include-step-id>/<child-step-id>`; child
   internal references acquire the same prefix. Reject every resulting collision.
3. A caller may reference only earlier request-bearing leaves, including earlier
   includes. It cannot reference the include node itself, a future include, a
   requestless child leaf, or a child's parameter namespace. Child source cannot
   access the parent's variables or responses except through explicit `with`.
4. Current `parameters` entries all have JSON-like default values. Omitted `with`
   entries use those defaults; unknown parameter names are errors. Null is a value,
   not a required-parameter marker. There is no new required/default/type schema.
5. Resolve `with` references in the caller scope at the include position. Child
   references remain in the child scope. Earlier caller response references are
   compiled symbolically, not evaluated by the loader or rewritten as child IDs.
   Actual response values are read only during the existing runtime preparation.
6. Substitution operates on recognized reference nodes, never on strings or an
   indiscriminate text replacement. Literal parameter objects resembling reference
   syntax stay literal data; they must not gain execution meaning on a second
   parse. Preserve reference identity where existing checks require a reference.
7. Each invocation has isolated parameter storage and compiled step objects.
   Generated parameter keys must not collide with caller keys or another call.
   Do not mutate child defaults, caller data, source documents, or another run.
8. Validate the fully instantiated plan again. Statically known invalid values at
   their use sites are declaration errors. Runtime-only missing/null response or
   unsupported value errors remain ERROR before the consuming action, followed by
   BLOCKED. Preserve false/zero, true/one, empty-string, and strict-type semantics.
9. Parameterization is allowed only in positions already supported by the current
   declaration contract. No parameterized IDs, targets, methods, counts, durations,
   check names, include targets, or mapping keys are added.
10. No structural override, deletion, selective execution, or disabling of a child
    step/assertion is permitted. `with` can instantiate existing assertion values;
    that effect must be visible in review and is not automatically approved.

Expansion is symbolic, not a transaction or a new runtime call frame. A runtime
input error occurs at its consuming leaf, just as in an equivalent flat flow;
earlier leaves may already have acted. There is no rollback or hidden up-front
evaluation of every runtime parameter. FAILED, ERROR, and SKIPPED stop all later
leaves, including the rest of the child and the parent's following steps.
COMPLETED and NOT_APPLICABLE retain their existing meanings, not asserted success.

The parent retains its ID, description, grid, and actor. Child grid and description
are source metadata, not additional filters or projection selectors. All adapters
receive the root Scenario and qualified leaf IDs, not a hidden switched context.
Existing adapter capabilities and projection restrictions still apply to the full
expanded flow. Inclusion cannot make an unsupported flow silently pass.

Equivalence means the same ordered actions, typed values, expectations, bindings,
polling, and stop behavior as an independently authored flat control. Compare
models after an explicit one-to-one renaming of leaf IDs and generated parameter
keys, ignoring only source annotations. Compare runtime traces/reports after also
excluding fresh trace IDs and timing. Do not claim raw dataclass equality or
generate the expected flat control by calling the expansion code under test.

## 5. Actor decision: identical actors selected

Current code stores actor on Scenario, not Step. Backend obtains one session per
projection; frontend/e2e use one session/context. Contract does not authenticate.

**Approved first slice:** parent and child actors must be exactly equal. A
mismatch is a DeclarationError for every projection, before any side effect.
Do not silently inherit, overwrite, impersonate, or switch the child's actor.
This preserves the flat execution model and makes repeated includes feasible
without adding a second orchestration system.

**Alternative, not included in this candidate's implementation scope:** permit
backend leaves to retain different child actors. That requires explicit per-step
identity, session acquisition/lifetime, adapter context, report, and flat-control
semantics. Frontend/e2e would need pre-execution rejection; contract would still
only consume backend evidence and never authenticate. Selecting this alternative
requires a targeted specification amendment before Stage B, not a developer choice.

The recommended slice does not solve a different-role setup followed by a
permission-rejection test. Do not claim that consumer has been migrated or use
actor substitution to make it appear supported.

## 6. Expansion view, reports, and confidentiality

Add `refracto validate <parent.yaml> --expand` as an explicit, read-only review
view. It uses the runtime loader and the same dependency checks, exits zero only
for a valid complete plan, and uses the existing invalid-declaration exit code 2.
An invalid dependency must not leave a partial plan on stdout. Ordinary `validate`
retains its summary behavior and does not dump parameters or call arguments.

The expanded view lists verified dependencies and hashes, root actor, qualified
leaf IDs, source Scenario/step, actions, expectations, and symbolic value wiring.
It preserves every assertion, and keeps runtime response values unresolved. It
does not authenticate, call adapters, normalize responses, or execute any action.
It is a review representation, not a second authoring format or a promise that
generated slash IDs can be pasted back as ordinary source step IDs.

Explicit expansion may display literal data already written in the declarations,
including defaults and `with` literals. Help text must warn that this output has
the source's confidentiality level; do not put credentials in declarations or
publish expansion logs by default. It never includes actual runtime bindings.
Use an explicit renderer, not generic `asdict(Scenario)` or `asdict(report)`.
New errors and default repr must not dump call values or raw dependency contents.

Keep qualified IDs in execution evidence, contract keys, and report steps/checks.
Provide a source lookup on the loaded Scenario and returned RunReport, keyed by
executed leaf ID, containing only source Scenario ID, source step ID, include
step ID (null for a parent leaf), and source-file SHA-256. Add it as independent
default, keyword-only diagnostic metadata, excluded from equality and default
repr. Runner aggregation may copy this metadata; it must not affect execution.

`localize()` keeps its existing tuple shape and failed-check-only semantics.
Its qualified step ID indexes the source lookup, including a failed contract
check. ERROR/BLOCKED are located through StepResult and the same lookup, not
misrepresented as newly supported `localize()` entries. Domain-level synthetic
errors need no invented child source. No new result status or approval status is
added. Strict execution success remains `report.status == "PASSED"`.

## 7. Negative tests and paired controls

Every rejection below must exercise the public loader/runner/CLI boundary where
applicable, with zero authentication, adapter calls, waits, and UI actions for
declaration failures. Use passing neighbors so over-rejection is also detected.
Record that new-feature tests fail before implementation and pass afterward;
already-covered rejection tests need not be artificially made red.

| Rule | Required rejection or counterexample | Passing neighbor |
| --- | --- | --- |
| R-a: one level | Self-include, child includes a third file, direct/indirect cycle. | One parent includes a leaf child. |
| R-b: static target | A parameter/response object or other non-string include target. | Literal mapped Scenario ID. |
| R-c: parameter scope | Unknown `with` key, undeclared parameter reference, wrong container, statically invalid substituted use. | Omitted override uses default; null is not a missing sentinel. |
| R-d: immutable structure | Include carries expect/poll/target/value/duration or unknown override fields. | Declared parameter value used in child body and expectation, both visible. |
| R-e: no hidden repetition | `repeat`/`times` or a call count expression. | Two explicit includes execute twice with separate IDs/results. |
| R-f: standalone validity | Child has no effective assertion; invalid check, duplicate key, alias, or unsafe tag. | Independently valid child included without invented parent assertions. |
| R-g: closed child scope | Child reads parent/sibling steps; caller references future/non-request child or include node. | Earlier parent response supplied explicitly through `with`. |
| R-h: namespace | Slash in source step IDs within composition, duplicate include IDs, generated collisions. | Same internal step ID in two distinct inclusions remains distinct. |
| R-i: pin | Missing/invalid pin, changed child bytes (including comment-only), mismatched declared ID. | Matching exact bytes; every later load checks again. |

Additional tests required for these same boundaries, not new capabilities:

- Test the selected pin format only. Sidecar/manifest-specific cases below apply
  to option B; option A instead tests its inline fields and repeated-pin agreement.
- Missing/malformed sidecar or dependency, duplicate/extra manifest keys, two IDs
  aliasing a file, forbidden local paths/symlinks, and attempted URI loads.
  Run from another cwd successfully; prove resolution does not perform network I/O.
- Replace a dependency on disk between verification and parsing; parsing must use
  only the checked buffer. Repeated calls in one load must see identical source.
- Exactly 64/65 distinct children and 1,000/1,001 expanded leaves demonstrate
  inclusive expansion limits; no partial plan or silent truncation.
- Parent/child actor mismatch refuses the whole plan; equal actor uses the existing
  single-session behavior. Child grid cannot cause hidden filtering.
- Repeated calls with same-named parameters and steps do not share or mutate data.
  Qualified references and contract identities select the correct invocation even
  with identical method/path. Child-internal IDs are rewritten; injected caller
  references are not accidentally rewritten as child-local references.
- Literal reference-looking objects do not become references; strict falsy values
  survive. Known invalid overrides fail before execution; runtime-only invalid
  response values fail before their consuming action and block subsequent leaves.
- FAILED, ERROR, and polling SKIPPED within a child stop the remaining child and
  parent actions. A successful child is executed again when included again.
- Expansion is deterministic for fixed bytes, prints no partial plan on error,
  and contains no runtime values. Sensitive call-value sentinels are absent from
  default validation/errors/report repr; explicit expansion's disclosure is tested
  and documented rather than incorrectly promised to be redacted.
- Source lookup identifies both a child assertion failure and a contract mismatch;
  preserve the `localize()` tuple API and ERROR reporting boundary.

## 8. Executable consumers and equivalence evidence

Stage B must add a neutral public child/parent example pair under `scenarios/`,
using the existing public Demo mappings, with executable tests collected by CI.
Use same-role creation followed by read/update; do not copy private fixtures.
The illustrative record names in section 2 are not a demand to invent new Demo
endpoints. Publish complete runnable examples with actual dependency pins.

Compare include and independently authored flat controls with identical actions,
assertions, response sources, and inputs. Exercise repeated inclusion, explicit
parameter handoff, response readback, and fail-fast in backend, plus offline
contract consumption. For a supported UI child, run frontend and live e2e with
real Chromium: one context per projection, unchanged action counts, ordered
mock responses, and qualified request ownership. Unsupported expanded flows must
be rejected before side effects. Do not infer UI safety solely from backend tests.

Child approval applies to a definition, not a whole parent goal. A parent can
validate with assertions supplied by a child alone; do not invent redundant
assertions to meet a count. Review must still identify which parent obligations
are unverified. Mechanism tests do not measure human review benefit.

Private consumer migrations are separate, later authorized work and are not a
completion gate for this public task. No private files are read or modified here.

## 9. Bounded fault-detection comparison

Do not build a general mutation engine. Reuse a fixed small set of public negative
controls: incorrect success for a declared rejection, changed target collection
content, and a wrong-object response/binding. Existing examples are in
`tests/test_second_adapter.py` and `tests/test_projection_backend.py`.

Before changing core in Stage B, freeze the actual three injected faults, flat
controls, commands, and expected observations in the test/acceptance assets.
Run the flat controls against baseline `9bebfa7` in a detached verification
worktree. Run equivalent flat and include controls against the candidate in an
isolated verification worktree. Use the same assertions, inputs, and evidence
channels; do not count newly stronger assertions as an include benefit.

Report each fault as detected, missed, invalid control, or not executed, with
commands and exit codes. A control must actually reach its fault; import/setup
errors are not detections. Report detected/valid-executed plus all exclusions;
zero valid executions means N/A. All three controls must be valid and executed
for acceptance. This is a bounded backend fault-injection comparison, not product
quality, a general mutation score, or evidence of unmeasured projections. Preserve
baseline evidence and clean up only the task's own verification resources.

## 10. Stage B scope, checks, and final gates

Expected implementation scope: declaration loader/expansion, CLI review output,
small diagnostic metadata additions and runner aggregation, tests, neutral demo
scenarios and pins, and documentation. Prefer reusing current preparation and
projection loops. Necessary value-validation fixes must be confined to preserving
the specified instantiated-plan semantics, not widening reference positions.
Do not add another orchestrator, per-step actors, adapter ports, auto-approval,
remote dependency fetches, a parameter type system, or report serialization.

On delivery, update SCENARIO.md with "Including a pinned, reviewed Scenario" and
the chosen dependency mechanism, and update the public roadmap only to the actual
delivery stage. Full Scenario examples must be loaded with their real companion
files and hashes in documentation tests. Fragments need their stated context;
do not claim a fragment or illustrative pin is independently executable.

Required local verification, with actual commands/results recorded:

```sh
uv run pytest
uv run pytest tests/test_opensource_litmus.py tests/test_repository_hygiene.py
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
git diff --cached --check
```

Also validate every maintained Scenario, run expansion/negative tests and the
fault controls, verify real Chromium tests are not skipped in the full environment,
and reproduce the existing CI core-only installation (dev extras only, no browser
or Demo dependency). Preserve the import-direction litmus: core must not import
adapters. Any CI configuration change needs a concrete necessity, not a new
pipeline for its own sake. No hosted CI/submission is initiated without separate
authorization.

The Stage B delivery report must distinguish declaration validity, review/pin
status, execution outcomes, and unverified obligations. Include the exact accepted
file list, independent audit results, before/after fault results, commands/exit
codes, remaining limits, and any rejected expansion requests. Keep the report
product-neutral. Finish unstaged, uncommitted, and unpushed; leave unrelated files
and private workspaces untouched. Do not claim approval or cognitive-cost savings
from synthetic tests.

## Recorded Stage B decisions

1. **Actor:** the maintainer selected the identical-actor first slice. The
   backend multi-actor alternative is not authorized. Contract never authenticates.
2. **Dependency pin:** the maintainer selected B (parent sidecar). Inline pins
   are not authorized. The Scenario plus its pin asset are reviewed together;
   neither is an approval certificate.

The approval covers the bounded include/reference expression and stated limits.
It does not authorize staging, commits, pushes, or changes to private workspaces.
Implementation must still pass independent audit and architect acceptance.
