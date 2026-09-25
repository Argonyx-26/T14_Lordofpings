from argus import settings
from argus.ingest import demo_window, load_all_events
from argus.ingest.clips import parse_clip
from argus.ingest.doors import load_door_events
from argus.ingest.gps import _debounced_areas, load_device_events
from argus.ingest.groundtruth import load_ground_truth
from argus.ingest.rates import rate_anomalies
from tests.conftest import needs_data


def test_clip_times_are_utc(cfg):
    clip = parse_clip("2018-03-15.14-50-01.14-55-01.school.G420", cfg)
    assert clip.start_t == 1521139801.0           # 14:50:01 EDT == 18:50:01 UTC
    assert clip.end_t - clip.start_t == 300
    assert clip.camera == "G420"


def test_demo_window_is_thirty_minutes(cfg):
    start, end = demo_window(cfg)
    assert end - start == 1800
    assert cfg.epoch_to_local(start) == "2018-03-15 14:50:00"


def test_rate_anomalies_flags_spike_only_after_history():
    times = {"a": [float(t) for t in range(0, 600, 60)] + [600.0 + i for i in range(10)]}
    hits = list(rate_anomalies(times, bucket_s=60, min_history=5, z_threshold=2.0))
    assert [h[1] for h in hits] == [600.0]


def test_debounce_ignores_single_fix_flicker():
    assert _debounced_areas(["a", "a", "b", "a", "a"]) == ["a"] * 5
    assert _debounced_areas(["a", "b", "b"]) == ["a", "b", "b"]


@needs_data
def test_door_events_come_only_from_door_annotations(cfg):
    events = load_door_events(settings.ANNOTATION_DIR, cfg)
    types = {e.type for e in events}
    assert types <= {"door_open", "entry", "exit", "door_surge"}
    assert sum(e.type == "door_open" and e.sensor_id == "G421-door" for e in events) == 11
    assert all(e.provenance in ("annotation_derived", "computed") for e in events)


@needs_data
def test_ground_truth_never_leaks_into_inputs(cfg):
    events = load_all_events(cfg)
    assert not any("steal" in e.type or "abandon" in e.type for e in events)
    gt = load_ground_truth(settings.ANNOTATION_DIR, cfg)
    assert [g.kind for g in gt].count("theft") == 4
    assert [g.kind for g in gt].count("abandoned_package") == 1


@needs_data
def test_gps_events_are_real_and_in_window(cfg):
    start, end = demo_window(cfg)
    events = load_device_events(settings.GPS_DIR, cfg, start, end)
    assert len(events) > 500
    assert all(start <= e.t <= end for e in events)
    assert {e.area for e in events} <= set(cfg.raw["areas"])
    assert all(e.provenance in ("recorded", "computed") for e in events)
