"""Forecast: projected scores are the real scorer's, the script stage is right, and responses rank by the stated rule."""
from argus.forecast import forecast, level, match_script, people_in_area, response_time
from argus.fusion.engine import FusionEngine
from argus.fusion.score import score_incident
from argus.schema import Entity, Event
from argus.uploads import assess
from tests.conftest import needs_data

T0 = 1521140000.0   # 14:53:20 local, daytime


def ev(i, source, etype, sev, conf=0.65, area="bus_station", t=T0, **attrs):
    return Event(event_id=f"f-{i}", t=t, source=source, sensor_id="X", zone=area, area=area, type=etype,
                 severity=sev, confidence=conf, provenance="computed", attrs=attrs)


def phone(i, etype, area, t, to=None):
    return Event(event_id=f"p-{i}", t=t, source="device", sensor_id="gps", zone=area, area=area, type=etype,
                 severity=0.02, confidence=0.6, provenance="recorded", entity=Entity(kind="device", id=f"d{i}"),
                 attrs={"to": to} if to else {})


def incident(cfg, *events):
    eng = FusionEngine(cfg)
    for e in events:
        eng.ingest(e)
    (inc,) = eng.incidents.values()
    return inc, eng.evidence(inc.incident_id)


def test_left_bag_follows_the_theft_script_and_next_stage_is_scored_for_real(cfg):
    inc, evidence = incident(cfg, ev(1, "cctv", "abandoned_object", 0.8, attrs_unattended_s=30))
    fc = forecast(inc, evidence, cfg, T0 + 10)
    assert fc["script"]["id"] == "theft"
    states = {s["id"]: s["state"] for s in fc["script"]["stages"]}
    assert states == {"left": "done", "taken": "next", "leaving": "later"}
    nxt = next(w for w in fc["whatifs"] if w["kind"] == "next_stage")
    assert nxt["signal"] == "custody_change"
    assert nxt["title"] == "Possible theft: unattended object taken" and nxt["title_changes"]
    # the projected score is exactly the scorer on evidence + the hypothetical signal at the playbook's strength
    t = cfg.playbook["typical"]["custody_change"]
    hyp = ev(9, "cctv", "custody_change", t["severity"], t["confidence"], t=T0 + 10)
    assert nxt["score"] == score_incident(evidence + [hyp], "bus_station", T0 + 10, cfg).score
    assert nxt["basis"] == "the detector's usual strength"


def test_other_sensors_night_profiles_and_dismissal_are_all_whatifs(cfg):
    log = [ev(1, "cctv", "abandoned_object", 0.8), ev(2, "door", "door_open", 0.05, t=T0 - 60),
           phone(3, "device_enter", "bus_station", T0 - 50)]
    inc, evidence = incident(cfg, log[0])
    fc = forecast(inc, evidence, cfg, T0 + 5, log=log)
    kinds = {w["kind"] for w in fc["whatifs"]}
    assert {"next_stage", "corroborate", "night", "profile", "dismiss"} <= kinds
    corroborate = [w for w in fc["whatifs"] if w["kind"] == "corroborate"]
    assert all(w["delta"] > 0 for w in corroborate)          # a second source always helps
    night = next(w for w in fc["whatifs"] if w["kind"] == "night")
    assert night["score"] >= fc["base"]["score"]
    dismiss = next(w for w in fc["whatifs"] if w["kind"] == "dismiss")
    assert dismiss["score"] < fc["base"]["score"]
    assert {w["label"] for w in fc["whatifs"] if w["kind"] == "profile"} == {
        "Under the Airport profile", "Under the School / college profile", "Under the Public park profile"}


def test_no_sensor_means_no_corroboration_whatif(cfg):
    inc, evidence = incident(cfg, ev(1, "cctv", "abandoned_object", 0.8))
    fc = forecast(inc, evidence, cfg, T0)                    # the log holds only the camera
    assert not [w for w in fc["whatifs"] if w["kind"] == "corroborate"]


def test_responses_rank_by_the_stated_rule(cfg):
    inc, evidence = incident(cfg, ev(1, "cctv", "abandoned_object", 0.8))
    fc = forecast(inc, evidence, cfg, T0)
    top = fc["responses"][0]
    assert top["action"] == "track_subject" and top["prevents_next"]      # stops "someone else takes it"
    assert top["time_to_effect_s"] == 0                                       # cameras act at once
    police = next(r for r in fc["responses"] if r["action"] == "notify_police")
    assert police["time_to_effect_s"] == cfg.raw["response"]["police_eta_s"]
    assert [r["rank"] for r in fc["responses"]] == list(range(1, len(fc["responses"]) + 1))


def test_guard_eta_is_walking_time_from_the_nearest_post(cfg):
    eta, basis = response_time("guard", "bus_station", cfg)
    assert 30 < eta < 600 and "Bus shelter patrol point" in basis
    assert response_time("guard", "upload", cfg)[0] is None                   # no layout for an uploaded clip


def test_people_in_area_follows_the_gps_stream(cfg):
    log = [phone(1, "device_enter", "bus_station", T0 - 30), phone(2, "device_enter", "bus_station", T0 - 20),
           phone(2, "device_exit", "bus_station", T0 - 10, to="plaza")]
    assert people_in_area("bus_station", log, T0) == 1
    assert people_in_area("bus_station", log, T0 - 15) == 2
    assert people_in_area("bus_station", [ev(1, "cctv", "running", 0.35)], T0) is None


def test_assault_script_prefers_the_furthest_stage(cfg):
    s = match_script(["device_crowding", "violence"], cfg)
    assert s["id"] == "assault" and max(s["reached"]) == 1
    assert level(90, cfg) == "critical" and level(10, cfg) == "low"


def test_upload_assessment_has_a_verdict_timeline_and_forecasts(cfg):
    events = [ev(1, "cctv", "abandoned_object", 0.8, area="upload"),
              ev(2, "cctv", "custody_change", 0.6, 0.8, area="upload", t=T0 + 20)]
    a = assess(events, "campus")
    assert a["verdict"]["incidents"] == 1 and a["verdict"]["level"] in ("high", "critical")
    assert a["verdict"]["headline"].startswith("Possible theft")
    assert [p["t"] for p in a["timeline"]] == [T0, T0 + 20]
    (iid,) = a["forecasts"]
    assert a["forecasts"][iid]["script"]["id"] == "theft"
    quiet = assess([ev(3, "cctv", "occupancy", 0.05, area="upload")], None)
    assert quiet["verdict"]["level"] == "clear" and quiet["incidents"] == []


@needs_data
def test_people_in_area_counts_gps_fixes_when_the_log_has_no_per_phone_events(cfg):
    """MEVA's GPS reaches ARGUS only as counts (ingest/gps.py), so the planner counts phones from the fixes."""
    from argus.ingest import demo_window
    start, _ = demo_window(cfg)
    n = people_in_area("bus_station", [ev(1, "cctv", "running", 0.35)], start + 900, cfg)
    assert isinstance(n, int) and n > 0
    assert people_in_area("live", [], start + 900, cfg) is None          # no outline to count in
