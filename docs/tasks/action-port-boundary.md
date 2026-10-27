# Action-port expectation and ownership boundary

## Status and authority

Approved specification, 2026-10-27. After reviewing this specification and the
threat model, the maintainer authorized development, independent audit, and
architect acceptance, followed by public submission after those gates pass.
Public starting main is `bb9c680`. Preserve the separately accepted R1
documentation revision. Implementation changes remain unstaged until final
acceptance. The subsequent task-branch/PR workflow must pass required PR and
main CI before cleanup. Private-workspace access is not authorized.

Sources are the maintainer's approved neutral requirements and the public code.
No private product mappings, paths, identifiers, or evidence belong in this task.
The [threat model](../threat-model.md) is approved as the scope of the guarantee;
implementation and acceptance evidence remain separate claims.

Development, independent audit and local architect acceptance subsequently
completed on 2026-10-27. The [acceptance record](action-port-boundary-acceptance.md)
records the tested scope, Python adapter migration, and remaining limitations.
PR/main checks and cleanup remain required publication gates.

## Purpose and non-goals

Operation adapters receive only the information needed to perform or map the
current operation. Core retains expectations, comparison, continuation, and
reporting. Remove unnecessary expectation exposure and shared declaration
references; preserve existing legitimate action inputs and explicit mock data.

This task reduces accidental coupling and mutation in in-process integrations.
It does not authenticate the truth of an adapter's observations, sandbox Python,
prove mappings faithful, or prevent a malicious adapter from reading files or
modifying process state. Mapping-fidelity experiments are a subsequent task.

No YAML change: keep `schema_version: 1`, current do/expect structure, one-level
inclusion, named results, users/sessions, and the R1 composition decision. Do not
add assertions, transformations, fallback values, report states, a binding DSL,
database observations, Flow execution, UI authoring, or a plugin security layer.
No R1 relaxation or exception is requested: this changes Python port inputs only.

## Verified starting points at bb9c680

- `backend.execute_api_step` calls `resolve_request` with the execution-local
  Scenario, a copied prepared Step, and a copied RequestTemplate. The Step
  includes resolved expectations; the Scenario argument itself is shared.
- `ui_stepwise.run` passes that Scenario to UI open and passes both Scenario and
  a copied prepared Step to UI perform. Copying a Step does not hide its contents.
- `_issue_permit` passes the entire resolved-binding map. Bindings can be needed
  only by assertions, so removing the Scenario and Step arguments is insufficient.
- Public Demo/Documents/minimal resolvers use request data rather than
  expectations. Demo UI uses its Step only for credential-header collision checks;
  BrowserSupport needs header names for that check, not expected header values.
- Existing request, traffic, recording, and normalization checks remain necessary.
  They do not establish independent provenance or certify arbitrary adapters.

## Approved Python interfaces

These signatures define the approved interface. There is no parallel legacy
call path after implementation.

### API request mapping

Introduce a small `RequestAction` value type in `refracto.ports`, with exactly:

| Field | Meaning |
| --- | --- |
| `method` | Current prepared logical HTTP method. |
| `path` | Current prepared, bound logical path; retain existing encoding rules. |
| `body` | Existing prepared business body or None, in an owned copy. |
| `query` | Existing prepared typed query map or None; preserve omission. |
| `headers` | Existing prepared business-header map or None. |

Use a frozen, slotted outer value with independently copied nested containers.
Freezing the outer object alone is not sufficient. Do not attach the declaration,
unbound expressions, all parameters, source lookup, result bindings, assertions,
future requests, or arbitrary metadata. Resolver inputs do not need credentials
or users: authentication and attribution remain at their existing ports.

```python
resolve_request(action: RequestAction) -> RequestSpec
```

Core constructs this view after binding. It retains a separate prepared request
for ownership checks and uses the existing query conversion/transport rules.
The resolver may map a logical route; it may not change declared business values.
The returned RequestSpec, its validation, and ApiDriver.send remain as today.
Update the Adapters resolver callable annotation to describe the new signature.

Backend's existing projection of a UI-associated request still treats that
declared request as its API operation. Its request data therefore legitimately
reaches the resolver. This does not authorize sending UI request expectations
to the browser action interface or expose response/state/UI assertions.

### Browser context and primitive action

Remove Scenario from context creation. Retain the established explicit fields:

```python
open_stepwise(
    session, *, mode, mock_plan=None, mock_queue=None,
    user=None, session_generation=0, context_id="",
) -> object

perform_step(
    context, permit: UiActionPermit, *, business_header_names: tuple[str, ...] = (),
) -> UiActionResult
```

Remove `resolved_bindings` from UiActionPermit. Keep only its existing operation
and authorization fields: execution/action/step IDs, mode, action, target, value,
token, effective user, session generation, and context ID. The value is the
prepared primitive input, not a general binding map. Core keeps resolved bindings
for comparisons and reports; binding-source and named-result reporting do not
lose information. Preserve qualified include step IDs and permit verification.

`business_header_names` is an immutable tuple of normalized lowercase, sorted
business-header names, empty when none are declared. Its only use is checking
collisions with session-owned credential headers before the primitive executes.
No expected header values, method/path/body/query from UI expect.request, or
response/frontend/state assertions may accompany it. BrowserSupport receives a
names-only validation call; update bundled UI adapters and the public example.
It must neither apply these names to traffic nor synthesize expected headers.

Context close and snapshot signatures stay unchanged. Core owns waits, sessions,
polling, evidence selection, and checks against actual browser requests. A wrong
query/body/header or absent/ambiguous action-associated request retains today's
failure classification. No independent API request may repair browser evidence.

### Deliberately unchanged interfaces

Authenticator, ApiDriver, ResponseNormalizer, StateProbe, and Recorder retain
their signatures and existing validations. Do not add expectation arguments to
them. Do not redesign the report model or require generic raw-field pointers.
No new core import from adapters or browser support is permitted.

## Ownership and allowed information

1. Each core-built action/request view contains only its allowlisted fields and
   resolved data. Core retains independent declaration, comparison, and report
   values. A new adapter input must not alias these through nested lists/maps.
   Returned data retained by core must not become a back reference through a
   reused input buffer. Preserve existing recording and normalization snapshots.
2. Legitimate action input can equal an expected value. That does not make the
   action input forbidden. Check which field supplied it, not a global blacklist
   of strings or keys. Literal business data may contain words such as `expect`.
3. Credentials and browser contexts are opaque adapter-owned handles. Preserve
   their identity and established lifecycle; do not indiscriminately deepcopy or
   reflect through them. Core must not place declarations inside such handles.
4. Explicit mock fixtures are authorized simulation inputs, not assertions.
   Preserve the existing shared run-local mock queue across user contexts and
   session replacement. Its consumption cursor is intentionally mutable; copying
   it per context would break ordering. Keep a separate retained fixture plan for
   core validation. A queue change cannot rewrite that plan or past evidence.
   Missing or altered fixtures must not fabricate success or fall through live.
5. Sensitive bodies, bound paths, query/header values, primitive inputs, permit
   tokens, credentials, and unnecessary binding values stay out of new default
   repr and error text. Preserve final report repr protections. No claim of safe
   arbitrary serialization or universal log redaction is added.

## Migration and bounded file scope

Expected implementation locations are `refracto/ports.py`, the Adapters annotation
in `refracto/runner.py`, request-view construction in `projection/backend.py`,
and UI calls/permit construction in `projection/ui_stepwise.py`. Add a small
shared helper only if needed for these boundaries; do not refactor the loader,
binding language, continuation policy, or normalizer as unrelated cleanup.

Migrate public Demo, Documents, and minimal resolvers; Demo and synthetic UI
adapters; BrowserSupport's names-only credential check; and all affected fakes,
test consumers, and maintained Python examples. Update onboarding, browser
support, and current port documentation when implementation is accepted.
Historical task/acceptance records remain historical. Target application behavior
and authored Scenario/include-pin bytes do not change.

This is an explicit Python adapter API break. Do not retry a new-signature failure
using the old signature, catch TypeError to pass a full Scenario, or add a shim
that restores expectation access. An incompatible adapter produces a visible
existing execution error; it must not silently skip, pass, or add an action.
Private adapters are not migrated in this task. Document the signature changes
for a separately authorized integration update.

## Mechanical acceptance matrix

Use existing public fakes and synthetic targets. Add a focused boundary test
module and browser integration cases; retain current tests rather than weakening
their assertions to accommodate the new signatures.

| ID | Required evidence |
| --- | --- |
| M1 | Inspect callable signatures and action transport fields. Scenario, Step, Expect, and Assertion types are absent from the narrowed inputs; the RequestAction and permit field allowlists are exact. A renamed generic metadata field cannot bypass the test. |
| M2 | Spy on real backend and explicit-API e2e resolver calls, plus frontend/mock and e2e/live UI open/perform calls. Current/future frontend, response, and backend_state assertion-only sentinels, including child assertions and parameters unused by the operation, never reach these operations. |
| M3 | A prior actual response value used only in a later assertion remains available to the core evaluator/report, but is absent from the later operation input. This specifically catches binding-map leakage through the permit. |
| M4 | Positive neighbors: the same string legitimately used as request input and expectation, and as UI fill value and rendering expectation, still reaches the correct action. Literal business dictionaries are not rejected by key-name blacklists. |
| M5 | Mutate nested body/query/header containers and retained input references. The original declaration, a later step, retained comparison values, and completed report evidence remain unchanged. A returned request changed against its declaration errors; changing an input alone cannot alter the comparison baseline. Test declared nested dictionaries/lists, not just a frozen outer field. |
| M6 | Real browser wrong query/body/header and absent/ambiguous primary traffic still fail through the established checks. Credential-name collisions stop the action without passing expected header values to the adapter. Names-only data is normalized and immutable. |
| M7 | Real frontend mocks remain explicit, ordered, and separate from live evidence. Cover multiple users, session replacement, repeated endpoints, missing/altered fixture data, and shared cursor consumption. Mutating the supplied plan/queue cannot rewrite retained expected fixtures or past results. |
| M8 | Existing behavioral regression: assertion failure continues unless stop is declared; unavailable dependencies block locally; ERROR and explicit SKIP retain stopping behavior; poll attempts, users/anonymous sessions, include/named results, unique/time scopes, query omission, header checks, and contract reuse are unchanged. Contract sends no extra requests. |
| M9 | Sensitive sentinels are absent from new default repr, boundary errors, and final report repr. Core import/litmus and offline dev-only execution remain independent of adapters and browser dependencies. |
| M10 | A legacy-signature resolver/UI consumer fails visibly under the existing execution rules, without a compatibility retry, fabricated evidence, or additional target action. |

For M2, also compare two valid declarations with identical prepared actions and
requests, user/session policies, explicit mocks, and business-header name sets.
Change only response/frontend/backend_state expectations with usable dependencies.
For corresponding operations reached in both runs, adapter-visible input content
must match except for fresh execution/authorization identities. This does not
require identical call counts: stopping policies and unavailable dependencies
can legitimately prevent later operations from being reached.

Structural spies inspect core-defined transport fields and built-in containers.
They do not recursively inspect arbitrary browser handles, credentials, function
closures, globals, or process memory. Tests must demonstrate their own sensitivity
with synthetic forbidden-field/nested-declaration and assertion-only-binding
injections; inspecting names or annotations alone is insufficient. These are
test probes, not a new runtime object-graph scanner.

Acceptance uses real loader/runner paths, unchanged public Demo with Chromium
live and explicit mocks, and the separate Documents API consumer. Include a
public mapping that maps logical routes without Scenario access. This establishes
the interface is sufficient for more than one synthetic integration; it does not
measure adoption cost or establish that all product mappings are correct.

## Validation and delivery gates

After implementation authorization, record exact commands, environment, counts,
and exit codes for the focused matrix, full suite with real Chromium and no
unexpected skips, fresh offline core environments matching supported Python CI,
litmus, document/example sentinels, `uv lock --check`, repository hygiene, and
unstaged/cached diff checks. Do not replace live-browser checks with fakes.
Verify vocabulary, Scenario YAML and include pins remain byte-identical to the
implementation starting baseline. Review the full public diff for source
neutrality; a hygiene script alone does not establish it.

Independent audit follows development and uses additional expectation-exposure
and mutation probes. Architect acceptance must name the accepted files and
remaining limitations. The maintainer's explicit publication instruction is
conditional on completing these gates; tests alone do not authorize submission.

Specification deliverables are this approved specification, a one-page threat
model, and a roadmap link. Implementation deliverables are narrowed ports,
migrated public consumers, mechanical tests, current interface documentation,
and a dated acceptance record. Agent review alone does not authorize an expanded
scope. If an actual consumer requires wider input, report the concrete
need before extending the allowlist; never restore the whole Scenario.

## Deferred provenance planning

Preserve two distinguishable future authoring routes: requirements/contracts as
the stated basis, and implementation-derived candidates explicitly marked as
such for stronger intent review. Mixed sources must be marked as mixed. A future
comparison should hold obligations, observation channels, fault sets, and review
effort comparable; source labels do not establish independence. This task adds
no authoring workflow, provenance schema, comparison benchmark, or approval UI.
