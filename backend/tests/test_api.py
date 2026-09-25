from fastapi.testclient import TestClient

from argus.api.main import app


def test_api_smoke():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"] is True
        cfg = client.get("/api/config").json()
        assert "bus_station" in cfg["areas"] and cfg["bookmarks"]
        clock = client.post("/api/replay", json={"cmd": "seek", "value": cfg["window"]["end_t"]}).json()
        assert clock["finished"] is True
        state = client.get("/api/state").json()
        assert state["summary"]["raw_events"] >= 0
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "snapshot"
        assert client.get("/api/incidents/NOPE").status_code == 404
        assert client.get("/api/audit").json()["verified"] is True


def test_console_is_served_when_built():
    from argus import settings
    if not (settings.REPO_ROOT / "frontend" / "dist" / "index.html").exists():
        import pytest
        pytest.skip("frontend not built")
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200 and "<div id=\"root\">" in r.text
        assert client.get("/api/health").json()["ok"] is True


def test_project_site_is_served():
    from argus import settings
    if not (settings.REPO_ROOT / "site" / "index.html").exists():
        import pytest
        pytest.skip("no site")
    with TestClient(app) as client:
        r = client.get("/site/")
        assert r.status_code == 200 and "We notice sooner" in r.text
        assert client.get("/site/fonts/geist-latin-wght-normal.woff2").status_code == 200


def test_supervisor_only_decisions_are_enforced_by_the_backend():
    """A duty officer can't dismiss, call the police or change the profile; the refusal writes nothing."""
    with TestClient(app) as client:
        cfg = client.get("/api/config").json()
        client.post("/api/replay", json={"cmd": "seek", "value": cfg["window"]["end_t"]})
        iid = next(iter(client.get("/api/state").json()["incidents"]))["incident_id"]
        before = len(client.get("/api/audit").json()["entries"])
        for body in ({"action": "dismiss", "note": "false_alarm"}, {"action": "escalate", "note": "notify_police"}):
            r = client.post(f"/api/incidents/{iid}/action", json={**body, "role": "duty_officer"})
            assert r.status_code == 403
        assert client.post("/api/profile", json={"name": "park"}).status_code == 403
        assert client.post("/api/profile", json={"name": "park", "role": "duty_officer"}).status_code == 403
        assert len(client.get("/api/audit").json()["entries"]) == before
