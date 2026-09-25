"""Pattern links, series, near-repeat watch and coverage: the rules as stated in patterns.py and coverage.py."""
from argus.coverage import coverage
from argus.fusion.engine import FusionEngine
from argus.intel import build_intel
from argus.patterns import walk_s
from argus.schema import Event

T0 = 1521140000.0   # 14:53:20 local


def ev(i, etype, area, t, sev=0.8, conf=0.8, source="cctv"):
    return Event(event_id=f"i-{i}", t=t, source=source, sensor_id="X", zone=area, area=area, type=etype,
                 severity=sev, confidence=conf, provenance="computed", attrs={"unattended_s": 60})


def run(cfg, *events, now=None):
    eng = FusionEngine(cfg)
    for e in events:
        eng.ingest(e)
    now = now if now is not None else max(e.t for e in events) + 5
    return eng, build_intel(list(eng.incidents.values()), eng.evidence, cfg, now, list(events))


def test_two_thefts_a_walkable_gap_apart_are_one_series(cfg):
    cafe = [ev(1, "abandoned_object", "school", T0), ev(2, "custody_change", "school", T0 + 20)]
    bus = [ev(3, "custody_change", "bus_station", T0 + 260)]            # 4 min later, 170 m away
    eng, intel = run(cfg, *cafe, *bus)
    assert len(eng.incidents) == 2
    (link,) = intel["links"]
    assert link["kind"] == "near_repeat" and link["script"] == "theft"
    assert link["shared_stages"] == ["Someone else takes it"]
    _metres, walk = walk_s("school", "bus_station", cfg)
    assert link["walk_s"] == walk and walk <= link["gap_s"]
    (s,) = intel["series"]
    assert s["incidents"] == [link["from"], link["to"]] and s["areas"] == ["school", "bus_station"]
    assert s["title"].startswith("2 bag thefts in")


def test_a_gap_nobody_could_walk_means_two_people(cfg):
    # same behaviour 60 s after the first, 220 m of path away (2:36 on foot): not one person
    _, intel = run(cfg, ev(1, "custody_change", "school", T0), ev(2, "custody_change", "bus_station", T0 + 60))
    (link,) = intel["links"]
    assert link["kind"] == "concurrent" and "two people" in link["why"]


def test_a_bag_left_is_not_enough_to_link(cfg):
    # a theft, then an unattended bag elsewhere: they share only the precursor, not the act
    _, intel = run(cfg, ev(1, "abandoned_object", "school", T0), ev(2, "custody_change", "school", T0 + 20),
                   ev(3, "abandoned_object", "bus_station", T0 + 900))
    assert intel["links"] == []


def test_same_behaviour_at_the_same_time_in_two_places_is_concurrent(cfg):
    _, intel = run(cfg, ev(1, "custody_change", "school", T0), ev(2, "custody_change", "bus_station", T0 + 1),
                   ev(3, "custody_change", "school", T0 + 30))
    (link,) = intel["links"]
    assert link["kind"] == "concurrent" and intel["series"][0]["concurrent"]


def test_phone_counts_alone_never_make_a_series(cfg):
    crowd = lambda i, a, t: ev(i, "device_crowding", a, t, sev=0.5, source="device")
    _, intel = run(cfg, crowd(1, "school", T0), crowd(2, "bus_station", T0 + 400))
    assert intel["links"] == [] and intel["watch"] is None


def test_links_only_use_what_has_been_seen_by_now(cfg):
    events = [ev(1, "custody_change", "school", T0), ev(2, "custody_change", "bus_station", T0 + 300)]
    eng = FusionEngine(cfg)
    for e in events:
        eng.ingest(e)
    early = build_intel(list(eng.incidents.values()), eng.evidence, cfg, T0 + 100, events[:1])
    assert early["links"] == []


def test_near_repeat_watch_ranks_the_site_and_lapses(cfg):
    _, intel = run(cfg, ev(1, "custody_change", "school", T0))
    w = intel["watch"]
    assert w["origin"] == "school" and w["remaining_s"] > 0
    assert [a["rank"] for a in w["areas"]] == list(range(1, len(w["areas"]) + 1))
    assert w["areas"][0]["weight"] >= w["areas"][-1]["weight"]
    assert sum(a["heightened"] for a in w["areas"]) == 2
    parking = next(a for a in w["areas"] if a["area"] == "parking")
    assert parking["blind"]                                             # no camera sees the parking lots
    _, later = run(cfg, ev(1, "custody_change", "school", T0), now=T0 + 1800 + 60)
    assert later["watch"] is None


def test_coverage_names_blind_spots_and_the_corroboration_ceiling(cfg):
    door = Event(event_id="d1", t=T0, source="door", sensor_id="D", zone="school_doors", area="school", type="entry",
                 severity=0.02, confidence=0.9, provenance="annotation_derived")
    cov = coverage(cfg, [door], T0)
    by = {a["area"]: a for a in cov["areas"]}
    assert by["school"]["ceiling"]["sources"] == 3 and by["school"]["ceiling"]["corroboration"] == 1.45
    assert by["parking"]["streams"] == {"cctv": False, "door": False, "device": True}
    assert "Bags left or taken" in by["parking"]["blind"]
    assert "live" not in by and "upload" not in by
    assert 0 < cov["visibility"] < 100
