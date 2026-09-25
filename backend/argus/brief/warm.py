"""Pre-generate LLM briefs for every incident in the demo window while online, so the demo runs offline.

Run from backend/:  python -m argus.brief.warm
Cached briefs live in data/cache/briefs.json and are keyed by incident evidence, so a replay reuses them.
"""
import os
import sys

from argus.brief.llm import brief_for
from argus.config import site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.replay.clock import Replay


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set (add it to .env in the repo root); briefs will stay on the template.")
    cfg = site()
    engine = FusionEngine(cfg)
    start, end = demo_window(cfg)
    events = load_all_events(cfg)
    replay = Replay(events, engine, start, end)
    # Step through the window so each incident is briefed with the evidence it has when it opens,
    # which is what the live replay will look up.
    seen: dict[str, int] = {}
    counts = {"llm": 0, "template": 0}
    t = start
    while t < end:
        t = min(t + 5, end)
        _, changed = replay.seek(t)
        for inc in changed:
            if inc.status in ("open", "ack", "escalated") and seen.get(inc.incident_id) != len(inc.event_ids):
                seen[inc.incident_id] = len(inc.event_ids)
                brief = brief_for(inc, engine.evidence(inc.incident_id), cfg)
                counts[brief.generated_by] += 1
                print(f"{inc.incident_id} score {inc.score:>3} [{brief.generated_by}] {brief.summary}")
    print(f"Done: {counts['llm']} LLM briefs cached, {counts['template']} template fallbacks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
