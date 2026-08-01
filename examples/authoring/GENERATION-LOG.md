# Generation log

Append one entry here each time the `refract-authoring` skill turns a human
case into a frozen scenario. The goal is to keep a visible record that the
middle layer was structured through capture and review, not hand-waved.

## Entry template

```text
## <date> — <case id>
* capture: observed method/path, response summary, span names and attributes
* mapping: oracle bullet -> bounded assertion term
* approval: person who confirmed the oracle
* artifact: scenarios/<file>.yaml
```

## 2026-07-21 — demo.item_update

* capture:
    * A real precondition created an item with `POST /items`.
    * The observed request was `PUT /items/1` with body `{"name": "renamed"}`.
    * The observed response was `200` with a success envelope carrying `itemId`.
    * The observed backend state included semantic span `item.update` with
      `row_count > 0`.
* mapping:
    * "The response succeeds and returns the updated itemId" -> `response.success` + `response.has(itemId)`
    * "Backend emits item.update and records a positive row count" -> `backend_state.span_exists(item.update)` + `backend_state.span_attr(item.update, row_count > 0)`
* approval: oracle confirmed by a human reviewer
* artifact: `scenarios/demo_item_update.yaml`
