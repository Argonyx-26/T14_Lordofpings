"""Duty officer vs supervisor: what each may see and do, enforced by the backend."""
import pytest
from fastapi.testclient import TestClient

from argus.api import main
from argus.api.main import app
from argus.audit import AuditLog
from argus.schema import Event

SUP = {"X-Argus-Role": "supervisor"}
T = 1521140000.0


def _ev(i, etype, sev=0.8):
    return Event(event_id=f"acc-{i}", t=T + i, source="cctv", sensor_id="G331", zone="bus_platform", area="bus_station",
                 type=etype, severity=sev, confidence=0.8, provenance="computed",
                 entity={"kind": "track", "id": f"G331:t{40 + i}"}, attrs={"unattended_s": 42, "raw_severity": sev})


@pytest.fixture()
def client(tmp_path):
    with TestClient(app) as c:
        main.rt.audit = AuditLog(tmp_path / "audit.jsonl")      # never write the demo's own log
        main.rt.engine.reset()
        for i, t in enumerate(["abandoned_object", "custody_change"]):
            main.rt.engine.ingest(_ev(i, t))
        yield c


def _iid():
    return next(iter(main.rt.engine.incidents))


def test_duty_officer_gets_evidence_without_detector_internals(client):
    r = client.get(f"/api/incidents/{_iid()}").json()
    assert r["role"] == "duty_officer" and "internals" not in r
    assert all(e["entity"] is None and "unattended_s" not in e["attrs"] for e in r["evidence"])
    s = client.get(f"/api/incidents/{_iid()}", headers=SUP).json()
    assert s["evidence"][0]["entity"]["id"].startswith("G331:t")
    sig = s["internals"]["signals"]
    assert {x["type"] for x in sig} == {"abandoned_object", "custody_change"} and any(x["counts_for_source"] for x in sig)
    (c,) = s["internals"]["contributions"]
    assert c["source"] == "cctv" and c["score_without"] == 0 and c["adds"] == s["incident"]["score"]


def test_the_whole_decision_log_and_its_export_are_a_supervisors(client):
    iid = _iid()
    client.post(f"/api/incidents/{iid}/action", json={"action": "ack"})
    assert client.get("/api/audit").status_code == 403
    mine = client.get(f"/api/audit?incident={iid}").json()
    assert mine["entries"] and all(e["incident_id"] == iid for e in mine["entries"])
    assert client.get("/api/audit/export").status_code == 403
    exp = client.get("/api/audit/export", headers=SUP)
    assert exp.status_code == 200 and iid in exp.text


def test_supervisor_reviews_dismissals_sees_what_was_learned_and_can_undo_it(client):
    iid = _iid()
    for path in ("/api/learning", "/api/dismissed"):
        assert client.get(path).status_code == 403
    assert client.post(f"/api/incidents/{iid}/action", json={"action": "dismiss", "note": "false_alarm"}, headers=SUP).status_code == 200
    rules = client.get("/api/learning", headers=SUP).json()["rules"]
    assert {r["type"] for r in rules} == {"abandoned_object", "custody_change"} and all(r["factor"] == 0.7 for r in rules)
    assert rules[0]["dismissals"][0]["incident_id"] == iid
    assert [i["incident_id"] for i in client.get("/api/dismissed", headers=SUP).json()["incidents"]] == [iid]
    # a duty officer cannot reopen; a supervisor can, and the lesson is taken back
    assert client.post(f"/api/incidents/{iid}/action", json={"action": "reopen"}).status_code == 403
    r = client.post(f"/api/incidents/{iid}/action", json={"action": "reopen"}, headers=SUP)
    assert r.status_code == 200 and r.json()["incident"]["status"] == "open"
    assert client.get("/api/learning", headers=SUP).json()["rules"] == []
    assert client.post(f"/api/incidents/{iid}/action", json={"action": "reopen"}, headers=SUP).status_code == 409


def test_supervisor_can_reset_one_lesson(client):
    iid = _iid()
    client.post(f"/api/incidents/{iid}/action", json={"action": "dismiss"}, headers=SUP)
    assert client.post("/api/learning/reset", json={"area": "bus_station", "type": "custody_change"}).status_code == 403
    assert client.post("/api/learning/reset", json={"area": "bus_station", "type": "custody_change"}, headers=SUP).status_code == 200
    assert [r["type"] for r in client.get("/api/learning", headers=SUP).json()["rules"]] == ["abandoned_object"]


def test_with_a_pin_set_the_supervisor_role_needs_it(client, monkeypatch):
    monkeypatch.setenv("ARGUS_SUPERVISOR_PIN", "4821")
    assert client.get("/api/config").json()["supervisor_pin_required"] is True
    assert client.get("/api/role", headers=SUP).status_code == 401
    assert client.get("/api/role", headers={**SUP, "X-Argus-Pin": "0000"}).status_code == 401
    assert client.get("/api/role", headers={**SUP, "X-Argus-Pin": "4821"}).json()["role"] == "supervisor"
    # the older body-role decision endpoints are held to the same PIN
    r = client.post(f"/api/incidents/{_iid()}/action", json={"action": "dismiss", "role": "supervisor"})
    assert r.status_code == 401
    assert client.get("/api/role").json()["role"] == "duty_officer"


def test_the_brief_follows_the_evidence_after_a_model_has_written_one(client, tmp_path, monkeypatch):
    """Once a language-model brief exists it used to stay, however the incident changed; now a change in evidence
    brings the brief for the new evidence."""
    import time

    from argus.brief import llm
    from argus.schema import Brief
    monkeypatch.setattr(llm, "CACHE_FILE", tmp_path / "briefs.json")
    monkeypatch.setattr(llm, "llm_brief", lambda inc, ev, cfg: Brief(
        summary=f"model brief for {len(ev)} signals", why="-", action_id="monitor", evidence_ids=[ev[0].event_id],
        generated_by="llm", model="test"))
    main.rt.engine.reset()

    def post(etype):
        r = client.post("/api/live/event", json={"type": etype, "severity": 0.9, "confidence": 0.8,
                                                 "bbox": [0, 0, 10, 10], "track": 1})
        return r.json()["incidents"][0]

    def summary(iid, want):
        for _ in range(100):
            b = client.get(f"/api/incidents/{iid}").json()["incident"]["brief"]
            if b and b["summary"] == want:
                return b["summary"]
            time.sleep(0.02)
        return b and b["summary"]

    iid = post("abandoned_object")
    assert summary(iid, "model brief for 1 signals") == "model brief for 1 signals"
    assert post("weapon_visible") == iid
    assert summary(iid, "model brief for 2 signals") == "model brief for 2 signals"
