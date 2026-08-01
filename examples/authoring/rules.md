# Generation rules: case -> scenario

This file is the human-readable source of truth for turning a
`examples/authoring/cases/*.case.yaml` file into a frozen `scenarios/*.yaml`
artifact. `.claude/skills/refract-authoring/SKILL.md` is the executable
checklist derived from these rules.

## The handoff boundary

`scenarios/*.yaml` is the artifact exchanged between the authoring side
(human + AI) and the deterministic execution side (the framework).

## Four hard rules

1. **Capture first.** Before writing a scenario, observe a real request against
   a running product and record the real request, response, and spans. Never
   invent paths, field names, or span names.
2. **Use only bounded vocabulary.** Scenario assertions must use terms that are
   already registered in `refracto/declaration/vocabulary.py`. If an oracle
   cannot be mapped cleanly, stop and report it instead of forcing procedural
   logic into YAML.
3. **Humans confirm the oracle.** The oracle always comes from the human.
   AI may structure it, but must not invent expected behavior.
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
| Page shows an anchor | `frontend: {check: visible, anchor: ...}` |
| Anchor count is greater than `n` | `frontend: {check: count_gt, anchor: ..., n: ...}` |
| Frontend/client sends `METHOD PATH` | `request: {check: request, method: ..., path: ...}` |

If an oracle cannot be mapped to this bounded vocabulary, stop and report it.
