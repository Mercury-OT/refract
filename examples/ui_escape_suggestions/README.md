# Dismiss search suggestions with Escape

This executable synthetic consumer checks three explicit operations: open the
page, fill the search input, then press Escape. It first observes the expanded
suggestions panel; afterwards the panel must be hidden and the typed value must
remain unchanged. The same Scenario and adapter run on listener and property
event-handler implementations, in frontend and live e2e modes.

From the repository root, with the demo/browser dependencies and Chromium installed:

```sh
uv run python -m examples.ui_escape_suggestions.run
```

The command requires all four native reports to be PASSED and exits nonzero for
any other result. Output includes statuses and check outcomes, not actual input
values or raw browser evidence. There are no API requests or response fixtures;
frontend supplies an explicit empty mock plan. Live e2e is actual browser execution,
not independent corroboration of the frontend run.

The input's `suggestions_visible` field comes from its actual associated panel's
visibility. Missing input, panel, or association is an error, never evidence that
the panel is closed. The adapter only maps operations and reads DOM state: it does
not hide the panel, repair focus, or replace Escape with a click. The input must
stay mounted and focused through delivery and collection. This example does not
cover dialogs which move focus, HTTP cancellation, arbitrary shortcuts, or all
autocomplete behavior. `reader` is a synthetic execution identity, not proof of
authentication or authorization behavior.

`target-sources.json` records the application sources before adapter integration.
The executable verifies their hashes before and after each run. Fault tests alter
served responses without rewriting those sources: ignored Escape, cleared text,
never-opened suggestions, wrong focus, duplicate inputs, missing/ambiguous panels
and broken association must not pass. These are bounded capability controls, not
product adoption or measured maintenance-cost evidence.
