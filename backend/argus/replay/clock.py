"""Replays a recorded window through the fusion engine at a chosen speed.

The clock is driven by the caller (`advance(wall_dt)`), so the API loop, tests and the evaluation
script all share the same code path. Seeking rebuilds engine state by fast-forwarding from the start,
which keeps every view deterministic.
"""
import bisect

from argus.fusion.engine import FusionEngine
from argus.schema import Event, Incident


class Replay:
    def __init__(self, events: list[Event], engine: FusionEngine, start_t: float, end_t: float,
                 speed: float = 10.0):
        self.events = sorted(events, key=lambda e: (e.t, e.event_id))
        self._times = [e.t for e in self.events]
        self.engine = engine
        self.start_t, self.end_t = start_t, end_t
        self.speed = speed
        self.playing = False
        self.reset()

    def reset(self) -> None:
        self.engine.reset()
        self.sim_t = self.start_t
        self._idx = 0

    @property
    def finished(self) -> bool:
        return self.sim_t >= self.end_t

    def advance(self, wall_dt: float) -> tuple[list[Event], list[Incident]]:
        if not self.playing or self.finished:
            return [], []
        return self._run_to(min(self.sim_t + wall_dt * self.speed, self.end_t))

    def seek(self, t: float) -> tuple[list[Event], list[Incident]]:
        t = max(self.start_t, min(t, self.end_t))
        if t < self.sim_t:
            self.reset()
        return self._run_to(t)

    def _run_to(self, t: float) -> tuple[list[Event], list[Incident]]:
        stop = bisect.bisect_right(self._times, t)
        new_events = self.events[self._idx:stop]
        changed: dict[str, Incident] = {}
        for ev in new_events:
            for inc in self.engine.ingest(ev):
                changed[inc.incident_id] = inc
        self._idx = stop
        self.sim_t = t
        return new_events, list(changed.values())

    def run_all(self) -> None:
        self._run_to(self.end_t)
