"""Loads site.yaml, areas.geojson and playbook.yaml into one SiteConfig."""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml
from shapely.geometry import Point, shape
from shapely.prepared import prep

from argus.settings import CONFIG_DIR


@dataclass
class SiteConfig:
    raw: dict
    playbook: dict
    area_shapes: dict = field(default_factory=dict)

    @property
    def utc_offset(self) -> timedelta:
        return timedelta(hours=self.raw["utc_offset_hours"])

    @property
    def fps(self) -> int:
        return self.raw["fps"]

    @property
    def fusion(self) -> dict:
        return self.raw["fusion"]

    @property
    def rates(self) -> dict:
        return self.raw["rates"]

    def camera(self, sensor_id: str) -> dict:
        return self.raw["cameras"].get(sensor_id, {"zone": sensor_id, "area": "unknown", "label": sensor_id})

    def area_name(self, area: str) -> str:
        return self.raw["areas"].get(area, {}).get("name", area)

    def criticality(self, area: str) -> float:
        return self.raw["areas"].get(area, {}).get("criticality", 0.5)

    def area_at(self, lat: float, lon: float) -> str | None:
        p = Point(lon, lat)
        for area, poly in self.area_shapes.items():
            if poly.contains(p):
                return area
        return None

    def local_to_epoch(self, local: str) -> float:
        """'2018-03-15 14:50:00' (site local time) -> UTC epoch seconds."""
        naive = datetime.strptime(local, "%Y-%m-%d %H:%M:%S")
        return (naive - self.utc_offset).replace(tzinfo=timezone.utc).timestamp()

    def epoch_to_local(self, t: float) -> str:
        return (datetime.fromtimestamp(t, timezone.utc) + self.utc_offset).strftime("%Y-%m-%d %H:%M:%S")

    def bookmarks(self) -> list[dict]:
        return [{"label": b["label"], "t": self.local_to_epoch(b["t_local"])} for b in self.raw.get("bookmarks", [])]


def load_site(config_dir: Path = CONFIG_DIR) -> SiteConfig:
    raw = yaml.safe_load((config_dir / "site.yaml").read_text())
    playbook = yaml.safe_load((config_dir / "playbook.yaml").read_text())
    geo = json.loads((config_dir / "areas.geojson").read_text())
    shapes = {f["properties"]["area"]: prep(shape(f["geometry"])) for f in geo["features"]}
    return SiteConfig(raw=raw, playbook=playbook, area_shapes=shapes)


@lru_cache(maxsize=1)
def site() -> SiteConfig:
    return load_site()
