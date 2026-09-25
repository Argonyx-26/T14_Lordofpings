"""The investigator agent (argus/agent.py) with a scripted model: the tool loop, the forced finish, citations that
must come from the log, no looking into the future, and the offline fallback. No network, no MEVA data."""
import argus.agent as agent
from argus.fusion.engine import FusionEngine
from argus.schema import Event

T0 = 1521141490.0   # 15:18:10 local


def ev(i, etype, sev, t=T0, source="cctv"):
    return Event(event_id=f"e-{i}", t=t, source=source, sensor_id="G331", zone="bus_platform", area="bus_station",
                 type=etype, severity=sev, confidence=0.65, provenance="computed",
                 attrs={"object": "backpack", "owner_left_scene": True})


def case(cfg, now=T0 + 60):
    eng = FusionEngine(cfg)
    events = [ev(1, "abandoned_object", 0.8), ev(2, "device_crowding", 0.44, T0 + 20, "device")]
    for e in events:
        eng.ingest(e)
    return agent.Case(events, list(eng.incidents.values()), now, cfg, evidence=eng.evidence)


def scripted(calls):
    """A fake Gemini that makes the given function calls, one per turn."""
    turns = iter(calls)

    def post(body):
        name, args = next(turns)
        return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}}]}
    return post


def test_tool_loop_runs_tools_and_keeps_only_real_citations(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_LLM", "on")
    monkeypatch.setattr(agent, "GEMINI_KEY", "test")
    monkeypatch.setattr(agent, "CACHE_FILE", tmp_path / "agent.json")
    c = case(cfg)
    (iid,) = c.incidents
    monkeypatch.setattr(agent, "_post", scripted([
        ("list_incidents", {}),
        ("get_incident", {"incident_id": iid}),
        ("search_signals", {"area": "Bus station", "source": "cctv"}),
        ("finish", {"answer": "A backpack was left.", "verdict": "likely", "confidence": 0.7,
                    "next_step": "Send a guard.", "cited_ids": [iid, "e-1", "INC-9999", "cctv-made-up"]}),
    ]))
    steps = []
    out = agent.investigate("What happened?", c, on_step=steps.append, replay_delay_s=0)
    assert out["generated_by"] == "agent" and out["verdict"] == "likely"
    assert [s["tool"] for s in out["steps"]] == ["list_incidents", "get_incident", "search_signals"] == \
        [s["tool"] for s in steps]
    assert out["cited_incidents"] == [iid]
    assert [e["event_id"] for e in out["cited_events"]] == ["e-1"]
    assert "1 incident raised" in out["steps"][0]["summary"]
    # a rehearsed question replays from the cache, same trace, with the network gone
    monkeypatch.setattr(agent, "_post", lambda body: None)
    again = agent.investigate("What happened?", c, replay_delay_s=0)
    assert again["cached"] and again["answer"] == out["answer"]


def test_step_budget_forces_finish(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_LLM", "on")
    monkeypatch.setattr(agent, "GEMINI_KEY", "test")
    monkeypatch.setattr(agent, "CACHE_FILE", tmp_path / "agent.json")
    seen = []

    def post(body):
        allowed = body["toolConfig"]["functionCallingConfig"].get("allowedFunctionNames")
        seen.append(allowed)
        call = ("finish", {"answer": "done", "verdict": "unclear", "confidence": 0.5, "next_step": "-",
                           "cited_ids": []}) if allowed else ("list_incidents", {})
        return {"candidates": [{"content": {"parts": [{"functionCall": {"name": call[0], "args": call[1]}}]}}]}
    monkeypatch.setattr(agent, "_post", post)
    out = agent.run("Loop forever?", case(cfg))
    assert out["generated_by"] == "agent" and len(out["steps"]) == agent.MAX_STEPS - 1
    assert seen[-1] == ["finish"]


def test_tools_never_see_the_future(cfg):
    c = case(cfg, now=T0 + 5)                 # the crowding signal at T0+20 has not happened yet
    assert c.search_signals()["matched"] == 1
    assert c.look_at_camera("what is there?", camera="G331", time="15:25:00")["error"] == "that moment is in the future"
    assert "future" in c.phones_in_area("Bus station", "15:25:00")["error"]


def test_offline_fallback_is_plain_and_cites_the_incident(cfg, monkeypatch, tmp_path):
    monkeypatch.setenv("ARGUS_LLM", "off")
    monkeypatch.setattr(agent, "CACHE_FILE", tmp_path / "agent.json")
    c = case(cfg)
    out = agent.investigate("What happened?", c)
    assert out["generated_by"] == "template" and "language model is offline" in out["answer"]
    assert out["cited_incidents"] == list(c.incidents)
    assert [s["tool"] for s in out["steps"]] == ["list_incidents", "get_incident"]
