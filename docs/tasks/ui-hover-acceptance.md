# Explicit UI hover verification

Approval date: 2026-11-02. Verification date: 2026-11-03.
Starting main: `272dad74f9fe51f8c32e4c7842267af143977c5b`.
Specification: [bounded UI hover](ui-hover.md).

Status: PASS. Development, independent core/browser audits and final architect
acceptance passed on 2026-11-03. The complete guarded suite passed 5839 tests and
reported successful cleanup. Submission was explicitly authorized after these
gates. Hosted PR/main CI, merge and branch cleanup are verified separately in the
associated PR and history; local acceptance is not a claim of hosted completion.

## Result and limits

The primitive moves the pointer once to a unique visible target, then evaluates
existing page checks. The complete consumer checks the item is initially hidden,
hovers to reveal it, and separately clicks it to request and display archived
records. CSS and JavaScript menu implementations use the same fixed target and
data; they are not independent products or adoption evidence.

Format 1, one-level inclusion, users/sessions, Flow scheduling and existing
assertions remain. Core validates an owned strict UiHover receipt and requires
driver opt-in before authentication or context creation. No action interface
receives expectations. A requestless backend step is NOT_APPLICABLE with UI
obligations not checked; a hover-only backend or contract selection is EMPTY.
Combining EMPTY backend with PASSED e2e remains DEGRADED. Pointer delivery is not
a product assertion and does not make an otherwise assertion-free Scenario valid.

The browser route pins the actual DOM object and an unobscured integer point
inside its in-viewport center geometry. It observes trusted movement and checks
identity/hit position through the final snapshot. It neither scrolls nor clicks,
focuses, alters styles or moves away and back. Tiny geometry without a valid
interior integer point is unsupported. A second movement at the same location
does not claim a second mouse-enter event. Unsupported document transitions are
guarded through the active action and the following idle gap.

Hover requests remain diagnostics. After the first hover in a mock context,
unassociated API traffic is blocked diagnostically for that context's remaining
lifetime. It cannot consume a later action's ordered fixture or reach a live
service. This includes delayed arrivals; no background-origin inference is made.
Live traffic and contexts without hover retain their existing behavior. A page
depending on background responses may therefore require live execution or a
separately reviewed extension. These are cooperative consistency controls, not
hostile-code attestation or rollback of application effects.

## Feasibility, corrections and independent review

Before repository implementation, 16 real Chromium feasibility cases passed:
actual CSS/JavaScript reveal, covered/missing/duplicate/hidden/replaced targets,
same-point movement, unsupported transitions, and immediate/deferred hover
requests remaining diagnostic across a following click. Retained mechanism
tests carry the accepted boundaries forward.

Development found that the existing mock collector lets unassociated background
requests consume ordered fixtures. The bounded post-hover policy above prevents
that interaction while retaining the prior non-hover behavior. Architect review
also required identifying the exact deliberately aborted request: a context-wide
flag alone could conceal an older request's actual CORS failure. The final native
collector uses a per-request marker, with three offline controls for unmarked
background, deliberately blocked background and foreground failures.

An early fractional-geometry control showed that Chromium can hit a tiny element
even when the floored center is outside its mathematical rectangle. The helper
now requires the chosen point inside both target rectangle and viewport.
An initial mixed-path regression command passed all 59 new mechanism controls,
then stopped at fixture discovery for an existing test; it is not recorded as a
passing complete run. The existing non-hover control passed separately, and the
browser regression group was rerun with its fixture scope intact.
That rerun passed all 188 Enter, form, native-await and existing mock controls;
the standalone 56-case hover suite also finished with exit 0 and complete cleanup.

The independent core reviewer passed 41 additional probes and 502 dev-only
regressions. They challenge identity/session reuse, strict types, unavailable or
wrong UI evidence, requestless references, mode capability, ownership and report
aggregation. The reviewer found no blocking issue and confirmed the vocabulary
hash is unchanged.

The independent browser/consumer reviewer passed 17 additional Chromium probes,
12 real consumer tests and the existing non-hover mock-background control
(30 total). Probes include held mouse buttons, hidden duplicates, mouse-leave
and synthetic callbacks during a later click, programmatic clicks from hover,
snapshot-time pointer displacement, delayed mock work and real CORS failures
after hover. No blocking issue remained. Review scripts used temporary scratch
files; permanent public regression files are the repeatable maintenance controls.

## Commands and verification

Paths below are repository-relative. Browser commands require installed Chromium.
Each guarded run uses a fresh output directory for progress, pytest log and final
exit/cleanup record. A fixture-discovery error is not a product failure or a pass.

| Command / environment | Actual result |
| --- | --- |
| Core developer: `uv run --locked --no-sync pytest -o addopts='' -q tests/test_ui_hover_core.py tests/test_ui_press_core.py tests/test_action_port_boundary.py tests/test_action_core.py tests/test_opensource_litmus.py tests/test_scenario_contract_doc.py` | 379 passed; 102 new hover core cases |
| Consumer: offline and real-browser consumer files | 14 offline and 12 Chromium tests passed |
| `uv run --locked --no-sync python -B -m examples.ui_hover_menu.run` | Four combinations PASSED; exit 0 |
| `refracto validate examples/ui_hover_menu/scenario.yaml --expand` | Approved three-step declaration expands successfully |
| Document fragments, exact consumer inventory and core import litmus | 67 passed |
| New helper tests plus exact-abort controls | 56 Chromium and 3 offline controls passed |
| Existing Enter, form, native-await and non-hover mock regression group | 188 passed; exit 0 and complete cleanup |
| Dev-only Python 3.11.15 and 3.12.13: `python -B scripts/run_tests.py --output-dir <fresh> --suite-timeout 600 -- -o addopts='' -q` | 4710 passed and one optional-dependency collection skip per version; successful exits and complete cleanup |
| Full Python 3.12.13: `uv run --locked --no-sync python -B scripts/run_tests.py --output-dir <fresh> -- -o addopts='' -q` | 5839 passed, one existing dependency deprecation warning, no skips; exit 0 and complete cleanup; 1003.5 seconds |
| `uv lock --check`, repository hygiene, `git diff --check`, cached diff check | Passed; hygiene and staged diff are checked again at submission |

The local full environment uses Playwright 1.62.0 and pytest 9.1.1. Hosted CI may
install a newer compatible browser dependency; local results are not substituted
for its required checks.

## Consumer, source review and scope

The [menu example](../../examples/ui_hover_menu/README.md) freezes app.py,
menu.css and menu.js before adapter integration. All hashes remain unchanged.
The host supplies one archived and one active record; the adapter does not seed
or repair business state. It maps actual DOM text and requires readable regions
before reporting an empty collection. The 116-line adapter measurement describes
physical source size, not authoring/review time or a comparative cost benefit.

Both normal implementations pass frontend mock and live e2e. Each reuses one
reader session/context and closes it once. Frontend sends zero API-server calls;
live e2e sends the declared filtered GET. Fault controls reject an ignored hover,
permanently visible menu, unavailable region, wrong rendering and ignored filter.
An API pass does not replace missing UI evidence. No storage or authentication
policy claim follows from the synthetic user's execution identity.

Sources are the public repository and newly authored neutral synthetic targets.
No private workspace, product source or evidence was accessed. Public text is
English and contains no private paths or product details. The assertion
vocabulary, dependency/workflow files, manifesto, existing declarations and
previous frozen target sources remain unchanged. Object absence stays paused.
No hover request association, object_id, new keys, pointer scripting, Flow
branching/editor or new assertion is included.

The accepted public scope is 34 files: six core modules, five browser modules,
six test files, ten files in the new menu example, and seven contract/task/status
documents. Executable and fixture hashes were frozen before the complete run
and rechecked afterwards. No workflow, dependency or unrelated file change is
accepted. Submission must use that exact scope and stop on unexpected changes.

## Maintainer summary

- A Scenario can explicitly hover, check the revealed UI, then click separately.
- Unavailable or ambiguous pointer/page evidence cannot be replaced with a pass.
- Hover/background traffic cannot borrow a later click's evidence or mock fixture.
- Real CSS/JavaScript menus and selected counterexamples pass their intended checks.
- Broader pointer geometry, hover requests and production adoption remain unproven.
