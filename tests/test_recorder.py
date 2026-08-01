from refracto import ports
from refracto.recorder import InMemoryRecorder


def test_inmemory_recorder_roundtrip():
    recorder = InMemoryRecorder()
    assert isinstance(recorder, ports.Recorder)
    resp = ports.RecordedResponse(
        status=200,
        headers={},
        json={"success": True},
        text="",
        trace_id=None,
        request=ports.RequestSpec("GET", "x"),
    )
    recorder.record(resp)
    assert recorder.responses() == [resp]
    recorder.responses().append("junk")
    assert len(recorder.responses()) == 1
