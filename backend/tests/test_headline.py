"""Guards the numbers we quote on stage. Runs where the real CCTV events exist (the demo laptop);
skipped elsewhere. If a tuning change breaks it, fix the change or update the pitch; never both silently."""
import pytest

from argus import settings

pytestmark = pytest.mark.skipif(not (settings.EVENTS_DIR / "cctv.jsonl").exists(),
                                reason="needs data/events/cctv.jsonl (demo laptop)")


def test_quoted_results_still_hold():
    from argus.eval.evaluate import run
    m = run()
    assert m["ground_truth_alerted"] >= 4, m["ground_truth"]
    assert m["false_incidents"] == [], m["false_incidents"]
    assert m["reduction"]["incidents_open"] + m["reduction"]["incidents_watch"] <= 5
