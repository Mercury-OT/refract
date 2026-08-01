from refracto import ports
from tests.fakes import FakeNormalizer


def _resp(json=None, status=200):
    return ports.RecordedResponse(
        status=status,
        headers={},
        json=json,
        text="",
        trace_id=None,
        request=ports.RequestSpec("POST", "p"),
    )


def test_fake_normalizer_maps_success_envelope():
    n = FakeNormalizer()
    norm = n.normalize(_resp({"success": True, "error": None, "data": {"itemId": 1, "count": 3}}))
    assert norm.succeeded is True
    assert norm.fields == {"itemId": 1, "count": 3}
    assert norm.status == 200


def test_fake_normalizer_failure_when_success_false():
    n = FakeNormalizer()
    norm = n.normalize(_resp({"success": False, "error": "nope", "data": None}))
    assert norm.succeeded is False


def test_fake_normalizer_synthesize_builds_stub_body():
    n = FakeNormalizer()
    body = n.synthesize({"itemId"})
    assert body["success"] is True
    assert "itemId" in body["data"]


def test_demo_normalizer_maps_envelope():
    from adapters.demo.normalizer import DemoResponseNormalizer
    n = DemoResponseNormalizer()
    norm = n.normalize(_resp({"success": True, "error": None, "data": {"itemId": 7}}))
    assert norm.succeeded is True and norm.fields == {"itemId": 7}
    assert n.synthesize({"itemId"})["data"] == {"itemId": "<stub:itemId>"}
