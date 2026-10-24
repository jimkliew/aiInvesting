import json

from aitrader.events import EventBus, read_trace


def test_emit_writes_trace_and_notifies(tmp_path):
    trace = tmp_path / "trace.jsonl"
    bus = EventBus(trace)
    bus.set_context(campaign="c1", season=2, phase="research", agent="idea")
    got = []
    bus.subscribe(got.append)
    bus.emit("hypotheses", n=3)
    bus.emit("agent_error", error="bad json")
    lines = trace.read_text().strip().splitlines()
    assert len(lines) == 2
    d = json.loads(lines[0])
    assert set(d) == {"ts", "seq", "campaign", "season", "phase", "agent", "kind", "payload"}
    assert d["kind"] == "hypotheses" and d["payload"] == {"n": 3} and d["season"] == 2
    assert [e.kind for e in got] == ["hypotheses", "agent_error"]
    assert [e.seq for e in got] == [1, 2]


def test_seq_continues_from_existing_trace(tmp_path):
    trace = tmp_path / "trace.jsonl"
    EventBus(trace).emit("a")
    bus = EventBus(trace)
    ev = bus.emit("b")
    assert ev.seq == 2
    assert [e.kind for e in read_trace(trace)] == ["a", "b"]


def test_broken_subscriber_does_not_stop_emit(tmp_path):
    bus = EventBus(tmp_path / "t.jsonl")

    def boom(ev):
        raise RuntimeError("x")

    bus.subscribe(boom)
    assert bus.emit("ok").kind == "ok"
