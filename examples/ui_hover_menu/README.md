# Hover a menu, then select a view

This executable consumer opens a records page, verifies that its archived-view
menu item is initially hidden, explicitly hovers the menu trigger, verifies the
item is visible, then clicks it as a separate action. The final step checks the
actual filtered request, response and displayed rows. A successful API response
cannot substitute for the preceding hover or its UI checks.

Run all four combinations from the repository root:

```bash
uv run --locked --no-sync python -B -m examples.ui_hover_menu.run
```

The process returns zero only when every native result is PASSED. Its JSON-lines
summary includes statuses, check outcomes and lifecycle counts, without raw
values or exception messages. The browser dependency and Chromium must be
installed. The command starts only temporary loopback HTTP listeners and closes
them and the browser contexts afterwards.

## Fixed application and integration

- `app.py` owns two host-prepared records: one archived and one active. The
  adapter does not create, repair or replace application data.
- `menu.css` implements a CSS hover menu. `menu.js` implements a second menu
  using mouse-enter/leave events when the page selects the JavaScript variant;
  both variants use the same real fetch and rendered list.
- `target-sources.json` freezes these three application files before adapter
  integration. The runner checks their hashes before and after execution. Fault
  controls inject isolated runtime changes without changing the frozen files.
- `scenario.yaml` holds the approved business checks. Logical targets map to
  ordinary selectors in `adapter.py`; anchors expose actual visible text. This
  example checks content, not stable UI business-object identity.
- The menu container, menu-content container and result region must be present
  unambiguously. A missing or unreadable required region is an observation error,
  not an empty list that can pass a zero-count assertion.
- `reader` is a synthetic logical-user binding. This example demonstrates shared
  execution identity; it does not claim to validate authentication policy.

The adapter contains 116 physical lines, including imports, whitespace and
comments. Browser startup, actual pointer delivery, request association,
recording, mocking and evidence identity are provided by BrowserSupport. This is
an inspectable integration size, not a measured human-effort or adoption benefit.

## Two selected projections

For each application variant the runner selects these separately:

| Projection | Request source | What this run establishes |
| --- | --- | --- |
| frontend | Explicit `mock-response.json` fixture | Actual hover, displayed menu/results and declared outgoing request, with zero API-server calls |
| e2e | Actual loopback API response | Actual hover and menu click, request, response and displayed results |

The mock fixture is a fixed input, never generated from expectations. Neither
hover nor opening the page has associated business request evidence. Only the
subsequent click owns the query. All three actions reuse one browser context.
This runner does not select backend or contract and does not imply that those
projections can prove hovering. The shared core documents requestless hover as
NOT_APPLICABLE there, with a hover-only backend run remaining EMPTY.

## Fault controls

The tests in `tests/browser/test_ui_hover_consumer.py` execute the same approved
Scenario against unchanged positives and isolated faults:

- Delivered hover but no visible menu: reveal fails, and the click is blocked.
- Permanently visible menu: the initial zero-count check fails before hovering.
- Missing required menu/result structure: observation errors, rather than a
  fabricated zero count.
- Correct API response with wrong displayed text: UI checks fail.
- HTTP 200 and success with an ignored filter: response/UI checks fail.

Both CSS and JavaScript positives run in mock and live modes in the test suite.
The consumer does not add focus repair, implicit clicks, scrolling, product
changes, hover request assertions or a new evidence channel. Pointer delivery is
a bounded browser-helper observation, not protection against hostile application
or adapter code in the same process.
