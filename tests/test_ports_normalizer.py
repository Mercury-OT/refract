from refracto import ports
from adapters.demo.normalizer import DemoResponseNormalizer
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


def test_normalizer_requires_no_synthesis_capability():
    assert ports.ResponseNormalizer.__abstractmethods__ == {"normalize"}
    assert isinstance(FakeNormalizer(), ports.ResponseNormalizer)


def test_demo_normalizer_maps_envelope():
    n = DemoResponseNormalizer()
    norm = n.normalize(_resp({"success": True, "error": None, "data": {"itemId": 7}}))
    assert norm.succeeded is True and norm.fields == {"itemId": 7}


def test_normalizers_do_not_invent_absent_response_fields():
    for normalizer in (FakeNormalizer(), DemoResponseNormalizer()):
        norm = normalizer.normalize(_resp({"success": True, "data": {"state": "ready"}}))
        assert norm.fields == {"state": "ready"}
        assert not hasattr(normalizer, "synthesize")
