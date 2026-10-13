"""Authored mock fixtures, independent from Scenario assertions and normalizers."""
from refracto import ports


def creation_plan(names=("ui-target",)):
    # This test explicitly assumes three rows per item and an initially empty
    # list. The app's follow-up GET has its own fixture, not a hidden overlay.
    plan = [ports.MockResponse(fixture_id="initial-list", source="demo fixture: empty list",
                               method="GET", path="items", response={"success": True, "data": {"items": []}})]
    items = []
    for i, name in enumerate(names, 1):
        plan.append(ports.MockResponse(fixture_id=f"create-{i}", source="demo fixture: created item",
            method="POST", path="items", response={"success": True, "data": {"itemId": i, "itemKey": str(i), "name": name, "count": 3}}))
        items = [*items, {"id": i, "name": name, "count": 3}]
        plan.append(ports.MockResponse(fixture_id=f"list-{i}", source="demo fixture: list response",
            method="GET", path="items", response={"success": True, "data": {"items": items}}))
    return plan
