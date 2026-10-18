# Generation rules: case -> scenario

This file is the human-readable source of truth for turning a
`examples/authoring/cases/*.case.yaml` file into a frozen `scenarios/*.yaml`
artifact. These are reviewable drafting rules, not an executable converter.
The previously referenced authoring skill is not distributed in this repository;
human or optional AI drafting must still obey the current `SCENARIO.md` contract.

## The handoff boundary

`scenarios/*.yaml` is the artifact exchanged between the authoring side
(human + AI) and the deterministic execution side (the framework).

## Four hard rules

1. **Separate requirements from observations.** Captures establish actual
   routes, fields, and span mappings; they do not define correct behavior.
   New features may start from approved requirements before a capture exists.
   Missing observations remain unverified, never invented.
2. **Use only bounded vocabulary.** Scenario assertions must use terms that are
   already registered in `refracto/declaration/vocabulary.py`. If an oracle
   cannot be mapped cleanly, stop and report it instead of forcing procedural
   logic into YAML.
3. **Humans confirm the executable declaration.** Review the exact structured
   YAML, including inputs, actions and assertions, not only its prose summary.
   AI may draft it, but must not invent or silently weaken expected behavior.
4. **Freeze once for reproducibility.** After a scenario is frozen into
   `scenarios/`, execution always uses that frozen file instead of regenerating
   it at runtime.

## Boundary against human deskilling

Spec-first testing is a spine, not the whole skeleton. Exploratory work still
matters. Discoveries from exploration should be fed back into new authoring
cases rather than reducing the human role to rubber-stamping.

## Mapping reference for the demo vocabulary

| Human oracle | Scenario assertion |
|---|---|
| Response succeeds | `response: {check: success}` |
| Response includes a field such as `itemId` | `response: {check: has, field: itemId}` |
| Backend emits semantic span `X` | `backend_state: {check: span_exists, span: X}` |
| Span `X` has an attribute comparison | `backend_state: {check: span_attr, span: X, attr: ..., op: ..., value: ...}` |
| Page shows an anchor | `expect.ui: [{check: visible, anchor: ...}]` |
| Anchor count is strictly greater than a threshold | `expect.ui: [{check: count_gt, anchor: ..., count: ...}]` |
| Frontend/client sends a request | `expect.request: {method: POST, path: [records]}` |
| Test directly sends a request | `do: {request: {method: GET, path: [records]}}` |

Use only `schema_version: 1`, explicit primitive steps, `parameters` and direct
response references. Preparation belongs in visible steps, not precondition
callbacks. `GENERATION-LOG.md` preserves historical evidence; its old YAML shapes
are not current templates. See `SCENARIO.md` at the repository root for the full
executable contract.

If an oracle cannot be mapped to this bounded vocabulary, stop and report it.
