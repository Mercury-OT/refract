"""Direct product-side checks for the demo app write endpoints (`PUT`/`DELETE`) and their semantic spans. These tests call the local demo app with `httpx`, generate a production-style traceparent, and read spans back from `/debug/traces/{trace_id}` without involving adapters."""
import httpx

from refracto.projection.backend import gen_traceparent


def _create(base_url, rows=(1, 2, 3)):
    r = httpx.post(f"{base_url}/items", json={"name": "x", "rows": list(rows)}, timeout=30.0)
    return r.json()["data"]["itemId"]


def _spans(base_url, trace_id):
    return httpx.get(f"{base_url}/debug/traces/{trace_id}", timeout=30.0).json()["spans"]


def test_put_updates_item_and_emits_item_update_span(demo_server):
    item_id = _create(demo_server)
    tp = gen_traceparent()
    r = httpx.put(f"{demo_server}/items/{item_id}", json={"name": "renamed"},
                  headers={"traceparent": tp}, timeout=30.0)
    body = r.json()
    assert body["success"] is True
    assert body["data"]["itemId"] == item_id

    spans = _spans(demo_server, tp.split("-")[1])
    by_name = {s["name"]: s for s in spans}
    assert "item.update" in by_name
    assert by_name["item.update"]["attributes"]["row_count"] > 0


def test_delete_removes_item_and_emits_item_delete_span(demo_server):
    item_id = _create(demo_server)
    tp = gen_traceparent()
    r = httpx.request("DELETE", f"{demo_server}/items/{item_id}",
                      headers={"traceparent": tp}, timeout=30.0)
    assert r.json()["success"] is True

    spans = _spans(demo_server, tp.split("-")[1])
    assert "item.delete" in {s["name"] for s in spans}

    items = httpx.get(f"{demo_server}/items", timeout=30.0).json()["data"]["items"]
    assert all(it["id"] != item_id for it in items)
