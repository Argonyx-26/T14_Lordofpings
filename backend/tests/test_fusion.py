from argus.fusion.engine import FusionEngine
from argus.fusion.score import score_incident
from argus.ingest import demo_window, load_all_events
from argus.replay.clock import Replay
from argus.schema import Event
from tests.conftest import needs_data

T0 = 1521140000.0   # 14:53:20 local


def ev(i, source, etype, sev, conf=0.6, area="bus_station", t=T0):
    return Event(event_id=f"t-{i}", t=t, source=source, sensor_id="X", zone=area, area=area, type=etype,
                 severity=sev, confidence=conf, provenance="computed")


def test_corroboration_raises_score(cfg):
    one = score_incident([ev(1, "cctv", "custody_change", 0.45, 0.5)], "bus_station", T0, cfg)
    two = score_incident([ev(1, "cctv", "custody_change", 0.45, 0.5),
                          ev(2, "device", "device_crowding", 0.44)], "bus_station", T0, cfg)
    assert two.score > one.score
    assert two.corroboration > one.corroboration


def test_repeats_from_one_source_do_not_inflate(cfg):
    once = score_incident([ev(1, "device", "device_crowding", 0.4)], "bus_station", T0, cfg)
    many = score_incident([ev(i, "device", "device_crowding", 0.4) for i in range(10)], "bus_station", T0, cfg)
    assert many.score == once.score


def test_weak_single_signal_is_not_an_alert_but_corroborated_one_is(cfg):
    eng = FusionEngine(cfg)
    eng.ingest(ev(1, "cctv", "custody_change", 0.45, 0.5))
    (inc,) = eng.incidents.values()
    assert inc.status in ("candidate", "watch")
    eng.ingest(ev(2, "device", "device_crowding", 0.44, t=T0 + 30))
    assert inc.status == "open"
    assert set(inc.sources) == {"cctv", "device"}


def test_routine_events_never_create_incidents(cfg):
    eng = FusionEngine(cfg)
    for i in range(200):
        eng.ingest(ev(i, "door", "door_open", 0.05, t=T0 + i))
    assert not eng.incidents
    assert eng.summary()["routine_events"] == 200


def test_signals_outside_window_start_new_incident(cfg):
    eng = FusionEngine(cfg)
    eng.ingest(ev(1, "cctv", "loitering", 0.3))
    eng.ingest(ev(2, "cctv", "loitering", 0.3, t=T0 + cfg.fusion["window_s"] + 1))
    assert len(eng.incidents) == 2


def test_dismissal_damps_future_scores(cfg):
    eng = FusionEngine(cfg)
    eng.ingest(ev(1, "cctv", "abandoned_object", 0.8, 0.8))
    first = next(iter(eng.incidents.values()))
    eng.act(first.incident_id, "dismiss")
    eng.ingest(ev(2, "cctv", "abandoned_object", 0.8, 0.8, t=T0 + 10))
    second = [i for i in eng.incidents.values() if i.incident_id != first.incident_id][0]
    assert second.score < first.score


@needs_data
def test_real_window_is_deterministic_and_quiet_without_video(cfg):
    events = load_all_events(cfg)
    start, end = demo_window(cfg)
    runs = []
    for _ in range(2):
        eng = FusionEngine(cfg)
        Replay(events, eng, start, end).run_all()
        runs.append([(i.incident_id, i.score, tuple(i.event_ids)) for i in eng.incidents.values()])
        s = eng.summary()
        assert s["raw_events"] == len(events)
        assert s["incidents_open"] == 0          # door + GPS alone must not page anyone
    assert runs[0] == runs[1]


@needs_data
def test_replay_seek_matches_straight_run(cfg):
    events = load_all_events(cfg)
    start, end = demo_window(cfg)
    a = Replay(events, FusionEngine(cfg), start, end)
    a.run_all()
    b = Replay(events, FusionEngine(cfg), start, end)
    b.seek(start + 900)
    b.seek(start + 300)      # rewind
    b.seek(end)
    assert a.engine.summary() == b.engine.summary()
