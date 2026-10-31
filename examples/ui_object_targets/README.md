# Object-owned controls in two list editors

Run the same [Scenario](scenario.yaml) against both independent browser layouts:

```sh
uv run --extra browser python -m examples.ui_object_targets.run
```

The six steps create a record through HTTP, open the list, click that record's
edit control, fill its name, save, and read it again through HTTP. Two other
records already exist; the created record is not first. The target, request,
response, and final read must agree on the actual record ID.

`target: records.edit_button` names the operation. `object_id` identifies the
business object that owns the control. The adapter describes the row selector,
relative control selector, and how to read an existing ID. The common browser
helper performs exact matching and refuses absent or ambiguous selections.

The table uses an ordinary record detail link. The card layout uses an ordinary
form action and native async/await. Neither target has test-only identity
attributes. Their source hashes in [target-sources.json](target-sources.json)
were frozen before the adapter and Scenario were written. The negative tests
use separate in-memory target subclasses; the normal sources stay unchanged.

These are two new synthetic front-end implementations with one shared HTTP
service, not two real products or evidence of adoption savings. The adapter
only maps actions, actual observations, requests, and a synthetic account. It
does not receive assertions or fabricate object IDs from desired values.
An HTTP read confirms the returned content; it is not independent database
evidence. Only the live e2e projection is claimed by this example.

The command prints actual step results, selections, request paths, changed
records, and source hashes. It exits nonzero unless both runs are `PASSED`.
Credentials are omitted from the printable summary. Chromium is required;
install it with `uv run --extra browser playwright install chromium` if needed.

The consumer tests also remove or duplicate the selected row and independently
misroute editing or saving. Missing and ambiguous rows must cause no edit
request. A mismatched request must not pass, even if a wrong-object side effect
has already happened. Selection evidence is a consistency check, not a sandbox
against malicious same-process adapter code.
