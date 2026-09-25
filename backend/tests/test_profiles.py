"""Security profiles (config/profiles.yaml): campus is the tuned site, airport is stricter, park looser."""
from argus.config import profiles, site
from argus.fusion.engine import FusionEngine
from argus.schema import Entity, Event, Media


def _bag(unattended_s: float, severity: float = 0.8) -> Event:
    return Event(event_id="cctv-G331-000001", t=site().local_to_epoch("2018-03-15 15:00:00"), source="cctv",
                 sensor_id="G331", zone="bus_platform", area="bus_station", type="abandoned_object",
                 severity=severity, confidence=0.7, entity=Entity(kind="track", id="G331:t1"), provenance="computed",
                 media=Media(clip="x", frame=0, bbox=[0, 0, 10, 10]), attrs={"unattended_s": unattended_s})


def test_campus_profile_is_the_tuned_site():
    base, campus = site(), site().with_profile("campus")
    for k in ("watch_threshold", "open_threshold"):
        assert campus.fusion[k] == base.fusion[k]


def test_airport_is_stricter_and_park_looser():
    a, c, p = (site().with_profile(n) for n in ("airport", "campus", "park"))
    assert a.fusion["open_threshold"] < c.fusion["open_threshold"] < p.fusion["open_threshold"]
    assert all(a.criticality(area) >= c.criticality(area) for area in site().raw["areas"])
    for prof in ("airport", "campus", "park"):          # weapons and violence reach a human everywhere
        assert "weapon_visible" in profiles()["profiles"][prof]["decisive"]


def test_park_needs_a_bag_alone_for_minutes():
    eng = FusionEngine(site().with_profile("park"))
    short = eng._apply_profile(_bag(unattended_s=20))
    assert short.severity < site().fusion["context_max_severity"]          # routine context in a park
    long = eng._apply_profile(_bag(unattended_s=180))
    assert long.severity >= 0.7


def test_airport_opens_an_unattended_bag_at_once():
    eng = FusionEngine(site().with_profile("airport"))
    [inc] = eng.ingest(_bag(unattended_s=16, severity=0.7))                 # owner merely away, not gone
    assert inc.status == "open" and inc.decisive
