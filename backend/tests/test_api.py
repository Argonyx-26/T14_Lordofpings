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
