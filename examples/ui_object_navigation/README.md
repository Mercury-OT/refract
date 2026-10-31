# Object selection across a full-document navigation

This example creates a record, opens its separate editor page from a list,
changes the name, saves and explicitly reads it again. The target has two
ordinary navigation implementations: a native anchor and a button whose
synchronous handler assigns the location. Both run the same
[Scenario](scenario.yaml) with the existing YAML structure.

Run after installing the optional browser dependency and Chromium:

```sh
uv run --extra browser python -m playwright install chromium
uv run --extra browser python -m examples.ui_object_navigation.run
```

The command succeeds only if both live e2e runs report PASSED. The browser retains
one user session across the document replacement. The record being edited is
not initially the first row. Identity comes from ordinary links/form routes,
not a label, position, inserted attribute or desired-value echo.

The navigation step has UI expectations and no API expectation. It checks the
actual editor's identity and name: a correct click receipt cannot excuse the
wrong destination. The new document's startup GET remains diagnostic. Its
subsequent explicitly declared save PATCH supplies action evidence, and the final
API read independently observes the response. The HTML document itself is not
normalized as an API response. API readback is not separate database evidence.

Normal [target sources](target-sources.json) were frozen before their adapter and
consumer checks were authored. The two navigation forms share server rendering,
the editor script, and the existing public records API service. The new adapter
also reuses that example's authentication and HTTP boilerplate. Thus this is a
bounded mechanism check, not two independent products or evidence of adoption
cost savings. Existing target sources were not changed.

The CI consumer tests run both real Chromium flows. Explicit faulty subclasses
serve another object's editor or save to the wrong record; the framework detects
both without repair requests. The wrong-save control records its actual side
effect instead of claiming rollback. Source hashes are checked before and after
execution, and all browser/server resources are closed.

Supported navigation is bounded to one same-origin successful HTML GET in the
same tab. Timers, asynchronous location changes, redirects, frames, new tabs,
form submissions and downloads are outside this slice. Missing or ambiguous
association must fail visibly; it cannot be replaced by matching URL or elapsed
time. See the [navigation specification](../../docs/tasks/same-tab-object-navigation.md).
