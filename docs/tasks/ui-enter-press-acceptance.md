# Enter press delivery record

Date: 2026-11-01. Starting main: `c3e750da54de85397049b07dcd19c797c0c81694`.
Specification: [bounded Enter](ui-enter-press.md).

Status: PASS. Development, independent core/browser audits and architect
acceptance passed on 2026-11-01. The maintainer authorized submission after these
gates; hosted PR/main checks, merge and branch cleanup are recorded separately in
the associated public PR and commit history. Local acceptance alone is not a
claim that hosted delivery has completed.

## Delivered boundary

Format 1 adds only a press leaf with a logical target and literal Enter. One-level
include, users/sessions, parameters, request/response/UI assertions and stopping
semantics remain. There is no automatic focusing, fallback click, API repair or
general key sequence. Drivers opt in explicitly; core validates a signed key and
an owned strict delivery receipt. Contract explicitly records that keyboard
delivery is outside its scope.

The browser helper requires one already-focused editable text/search input.
Trusted dispatch is rechecked, focus displacement is sticky, and nested synthetic
events cannot borrow Enter's origin. Its document guard covers the active press
and idle gap, then yields to the next authorized primitive's existing rules.
Native form activation/navigation, other keys, IME, frames and contenteditable
remain unsupported. ERROR cannot be read as proof of a product defect.

## Feasibility and independent review

Real Chromium exploration preceded implementation: 36 exploratory variants and
a final 12-case native-collector matrix. The initial naive key-handler change was
insufficient; nested inline change handlers and transient focus theft exposed
false association risks. Null synthetic-dispatch scope and sticky focus guards
closed those cases. Permanent browser controls carry these obligations forward.

Core development began with a real loader rejection of the new key field, then
added 109 bounded tests. The focused core/regression command passed 932 tests.
Independent core review found no blocking issue and ran 28 additional probes for
capability types/modes, receipt subclasses/counts, execution identities, forged
skips, diagnostic-only requests, missing mocks, ownership and closed grammar.
Its separate dev-only focused suite passed 390 tests. This review does not claim
browser correctness.

Browser development passed 78 real-Chromium cases. Independent browser/consumer
review found no blocking issue, passed 9 further Chromium probes and separately
reran all 13 live consumer tests. Those probes challenged retained-event
redispatch, parsed inline synthetic/native-await callbacks, timer-only evidence
under both transports, hidden duplicate handling, transient focus restoration,
native form submission and navigation during the final snapshot.

Architect review additionally required rechecking host-side errors and deadlines
after the final receipt read and before a subsequent action releases the idle
guard. Browser reads pump events, so checking only before the read was not enough.
Permanent tests cover both boundaries. The final full suite passed 5304 tests,
with one existing dependency deprecation warning and no skips.

Final approved-expression review restored the consumer's exact `submit_search`
step ID and `records.result_rows` observation anchor; development had renamed
those labels without need. Adapter, report reader and tests now use the approved
names, and a shape test protects them. The independent browser reviewer checked
this correction and unchanged target hashes; the 62-case consumer/documentation
rerun passed. The first full run was interrupted for this correction, is not
counted as a pass, and was restarted from the beginning.

## Consumer and scope of conclusions

The [search consumer](../../examples/ui_enter_search/README.md) runs the approved
open/fill/Enter sequence against real HTTP. Two keyboard handler forms share one
new server and static sample dataset; they are not two independent products.
Normal application source hashes were frozen before adapter and test authoring.
Mappings read actual input/row values, receive no expectations and never prepare
data, focus for press, alter the page or send a replacement API request.

Developer consumer checks: 13 tests passed and both CLI implementations PASSED.
Each normal run has one search request, one reader session/context and one close,
zero API-port sends, and one observed key down/up pair. Ignored Enter and focus
theft yield step ERROR; incorrect query or observed rendering yields FAILED.
RunReport aggregates these failed runs as FAILED under the existing convention.
UI checks cover the known positive/negative rows, not all possible extra rows,
all pagination, accessibility behavior or storage state.

## Commands and local verification

All paths below are repository-relative. Browser tests require installed Chromium.

| Command / environment | Result |
| --- | --- |
| `.venv/bin/python -m pytest -o addopts='' -q tests/test_ui_press_core.py` plus declaration, stepwise, object-target, user/session, action-port, query, runner/report, include and review regressions | 932 passed; includes 109 new core cases |
| `.venv-devonly/bin/python -m pytest -p no:cacheprovider tests/test_ui_press_core.py tests/test_action_port_boundary.py tests/test_scenario_include.py tests/test_scenario_review_exercise.py tests/test_stabilization_documentation.py` | Independent review: 390 passed |
| `.venv/bin/python -m pytest -o addopts='' -q tests/test_stabilization_documentation.py tests/test_opensource_litmus.py` | 52 passed |
| `.venv/bin/refracto validate examples/ui_enter_search/scenario.yaml --expand` | Valid expansion preserves the Enter key and existing structure |
| Dev-only Python 3.11.15 / 3.12.13: `python -m pytest -o addopts='' -q` | 4351 passed, 1 optional-dependency collection skip each |
| `.venv/bin/python -m pytest tests/browser/test_enter_search_consumers.py -q` | Developer: 13 passed |
| `.venv/bin/python -m pytest tests/browser/test_enter_press.py -q` | Developer: 78 real-Chromium tests passed |
| `uv run pytest -o addopts='' -q tests/browser/test_enter_search_consumers.py` | Independent browser audit: 13 passed |
| `.venv/bin/python -m examples.ui_enter_search.run` | Developer: both live handler forms PASSED, exit 0 |
| `uv run --locked --no-sync python -m pytest -o addopts='' -q` | Final architect run: 5304 passed, 1 existing Starlette/httpx warning, no skips; 821.09 seconds; exit 0 |
| `uv lock --check`, repository hygiene, `git diff --check` | Passed |

The documentation link inventory needed its explicit example count updated from
27 to 28; its initial failure was fixed rather than weakening the inventory.

The final full environment used Python 3.12.13, Playwright 1.62.0 and pytest 9.1.1.
Dev-only checks used Python 3.11.15 and 3.12.13. No current claim of hosted CI or
merge is made by these local results.

Independent exploratory probes used temporary scripts, not production changes.
Early browser probe harness attempts had import/fixture setup errors; those were
corrected before the complete successful run. They are not counted as product
failures or passing verification. Retained regression tests are the repeatable
public controls.

## Information-source and unchanged-scope review

Sources are the current public repository and newly authored neutral browser
fixtures. No private workspace, product source, internal name, private path,
customer measurement or private evidence was accessed or copied. Public text is
English; Chinese discussion remains outside the repository.

Object absence and Flow are not implemented. The assertion vocabulary,
dependency files, manifesto, existing Scenario files and prior frozen targets
remain byte-identical to the starting commit. This is evidence for the bounded primitive and its
controls, not proof of broad adoption benefit or hostile-code attestation.

## Accepted scope and maintainer summary

Accepted files are the eight changed core modules; three browser modules; six
test files; nine files under examples/ui_enter_search; and seven contract,
roadmap, threat, migration and task documents. No workflow/dependency change is
included. The public file list is frozen at submission; unexpected changes must
stop that sequence.

- Search can now be triggered by an explicit, observed Enter press.
- The input must already be uniquely selected and focused; no repair is hidden.
- Actual query/response/UI checks remain distinct from missing-evidence errors.
- Real Chromium controls and two search handler forms passed; this is bounded evidence.
- Other keys, native form/navigation, object absence and Flow remain outside scope.
