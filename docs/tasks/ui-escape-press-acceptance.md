# Explicit Escape verification

Approval and verification date: 2026-11-03.
Starting main: `1ae784df9e826aa820875d8987304cf506198cef`.
Specification: [bounded Escape](ui-escape-press.md).

Status: PASS. Development, supplemental independent audits and final architect
acceptance passed. The final post-repair full suite passed 6041 tests with complete
cleanup. The maintainer explicitly authorized submission after these gates;
the associated PR/history records hosted CI, merge and cleanup separately.

## Result and limits

The new literal Escape key reuses the existing press shape and owned UiKeyPress
receipt. It closes actual suggestions while preserving typed input in the
approved three-step consumer. Format 1, one-level includes, Flow, sessions and
assertion vocabulary remain unchanged. Capability is checked for each distinct
key before authentication/context creation. Escape supports page checks only;
Enter's form and request behavior is preserved.

The helper requires a unique visible editable text/search input already focused
and unchanged through collection. It does not repair focus, click elsewhere,
hide the panel or fabricate keyboard events. Dialogs that remove the input or
move focus remain unsupported. Invalid delivery is ERROR; actual delivery with
incorrect page behavior is FAILED. Backend/contract cannot prove this UI-only
obligation and remain EMPTY. Existing aggregate and stopping rules remain.

Escape callbacks have no request-evidence origin. After Escape or hover, the
helper blocks unassociated mock API requests for the remaining context lifetime,
including later Flow nodes. Such requests cannot consume later ordered fixtures
or reach live services. Custom drivers retain existing explicit diagnostic mock
rules; those diagnostics are not associated action/provider evidence. This is
cooperative consistency, not hostile-code attestation or universal browser support.

## Feasibility and corrections

Before implementation, actual Chromium showed a trusted Escape down/up pair with
no keypress event, panel dismissal, retained text and focus. Wrong-focus preflight
sent no key; synthetic events could change the panel but were distinguishable
from real delivery. The initial exploratory harness reused a document containing
top-level constants; its setup was corrected to fresh pages before recording the
passing feasibility result. Maintained browser tests cover these facts.

Architect review found the consumer's initial panel lookup checked uniqueness
only within its region. The final mapping also requires document-wide unique
input/panel IDs and actual ownership/association. Controls for duplicates outside
the region now fail rather than inventing false visibility. Target sources did
not change during this repair.

A larger browser regression exposed an intermittent paused-popup rejection stall
inside keyboard.down, before keyup or settling. The owned guard was interrupted
after collecting stacks (exit 130, cleanup complete); an isolated instrumented
reproduction timed out at 20 seconds (exit 124, cleanup complete). Neither counts
as a passing regression. The initial full suite was also deliberately stopped
for a clean post-fix run (exit 130, cleanup complete).

Closing only the paused secondary tab left the opener's input dispatch pending.
The bounded repair closes the collector's owned BrowserContext without resuming
the rejected target or entering a renderer. Normal failure cleanup still owns
the browser and Playwright. Eight instrumented popup attempts then completed;
ten retained popup/unsupported-transition checks passed, along with two offline
ownership/no-resume controls. Real Enter/Escape controls require no target HTTP.
No new target, navigation or authentication support is implied.

The complete post-repair browser regression passed 278 checks in 260.08 seconds,
exit 0 and complete cleanup without diagnostic requests. It combines existing
Enter, native-form and hover behavior with 62 Escape controls, mock acquisition
and rejected-context cleanup. The interrupted earlier run is not substituted
for this completed rerun.

## Independent review and retained checks

The independent core audit passed 35 additional probes and 686 focused regressions,
plus direct rejection of a response reference to requestless Escape. Probes cover
strict types, mixed key modes, identity, owned copies, false versus zero, failure
aggregation, sensitive diagnostics and EMPTY projections. No blocking finding.
Its custom-driver diagnostic fixture observation led to the explicit policy
clarification above, not a new core scheduling contract.

The initial independent browser audit passed 14 additional real Chromium probes
and 25 consumer checks (39 total). It covers held keys/modifiers, hidden duplicates,
focus theft/restoration, propagation stops, deferred native-await work crossing
into Enter, legacy/native mock isolation, frames and product-owned default
prevention. A setup error in its deliberately duplicated-input fixture was
corrected and the complete batch rerun; it was not a passing implementation test.
The popup repair then passed a supplemental independent audit: 53 checks under
a 30-second phase ceiling, exit 0 and complete cleanup in 41.6 seconds. These
include 14 new popup controls across live/mock, keydown/keyup and blank/HTTP/
blank-then-HTTP targets, the previous 14 probes and 25 consumer checks. Child HTTP
canaries stayed zero; browser disconnection and repeat-safe cleanup were checked.
Twelve rejected-target/lifecycle checks also passed. No remaining audit findings.

Durable public controls are in test_ui_escape_core.py, browser/test_escape_press.py,
test_browser_rejected_target_cleanup.py, test_ui_escape_consumer.py and
browser/test_ui_escape_consumer.py. Documentation fences and the exact executable
consumer are included in the existing documentation inventory. Temporary audit
probes provide additional review evidence, not an independently shipped test suite.

## Commands and final results

Use the repository root, browser dependencies and Chromium for browser commands:

```sh
python -m pytest tests/test_ui_escape_core.py tests/test_ui_press_core.py tests/test_ui_hover_core.py
python -m pytest tests/browser/test_escape_press.py tests/test_browser_rejected_target_cleanup.py
python -m pytest tests/test_ui_escape_consumer.py tests/browser/test_ui_escape_consumer.py
python -m examples.ui_escape_suggestions.run
python scripts/run_tests.py --output-dir /tmp/escape-full-check -- -o addopts='' -q
uv lock --check
bash scripts/check_repository_hygiene.sh
git diff --check
```

The full check output directory must be new. Dev-only checks use separate Python
3.11 and 3.12 environments with only `.[dev]`, the same guarded entry with a
600-second suite budget, and the existing offline litmus. Post-repair results in
both environments: 4834 passed and one optional collection skip, exit 0, complete
cleanup in 48.1 seconds each. This is not a claim of browser execution offline.
The documentation inventory, Scenario contract and offline litmus command passed
69 tests. Lock, hygiene, diff checks and byte-identical vocabulary checks passed.
The final full suite passed 6041 tests, zero skips, one existing third-party
Starlette/httpx deprecation warning, in 1092.57 seconds. The guard exited 0 in
1093.03 seconds, with no diagnostic request and complete cleanup. No production
code changed after this final regression began; subsequent edits record results.

## Information source and accepted boundary

Sources are the public implementation, maintainer-approved neutral expression,
new synthetic application and observed tests. The application and its listener/
property handlers were frozen before adapter integration; the exact inventory
is examples/ui_escape_suggestions/target-sources.json. The Scenario hash is
`e65c24facd548a43b2d5895381938874509e680bd6c700ce6a2fe6ad2498779b`.
Both implementations and frontend/e2e use the same declaration and mapping;
four native reports passed. They are not independent products or adoption proof.
The adapter has 94 physical / 72 nonblank noncomment lines; no cost-saving claim.

No existing product, private source, private workspace, graphical editor,
object-absence capability or declaration transformation is part of this delivery.
Public text is English and product-neutral. No assertion term or dependency was
added. Submission remains gated on completed local acceptance and the explicitly
authorized task branch, green PR checks, merge, green main checks and cleanup.
