"""Regression tests for the vision rules (backend/argus/vision/rules.py) on hand-built tracks.

They pin the behaviour behind the headline results, so a late tuning change can't silently break it:
an abandoned bag whose owner walks out, a bag carried off by someone else, and the negatives that keep the
false-incident count at zero (a seated owner keeping their bag, people walking normally).
Tracks are in the rules' own format: 30 fps clock, every 2nd frame, 1920x1072 pixels, an unknown camera
(no zones), exactly like an uploaded clip.
"""
import json

import pytest

pytest.importorskip("cv2")
from argus.vision.rules import ClipRules  # noqa: E402

STEM = "2000-01-01.12-00-00.12-01-00.test.UTEST"
PERSON, BACKPACK = 0, 24


def box(cx, cy, w, h):
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def person_at(cx, feet_y, h=300):
    return [cx - h * 0.3, feet_y - h, cx + h * 0.3, feet_y]


def lerp(a, b, t):
    return a + (b - a) * t


def run_rules(tmp_path, rows):
    path = tmp_path / f"{STEM}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in sorted(rows, key=lambda r: (r["frame"], r["tid"])):
            f.write(json.dumps(r) + "\n")
    return [e for e in ClipRules(path).run() if e["type"] != "occupancy"]


def det(frame, tid, cls, xyxy, conf=0.8):
    return {"frame": frame, "tid": tid, "cls": cls, "conf": conf, "xyxy": [round(v, 1) for v in xyxy]}


def test_bag_left_behind_when_owner_walks_out_is_abandoned(tmp_path):
    rows = []
    for f in range(0, 1800, 2):                                     # 60 s: the bag never moves
        rows.append(det(f, 50, BACKPACK, box(1000, 700, 60, 60)))
    for f in range(0, 602, 2):                                      # owner stands at it 10 s, then walks out right
        x = 1000 if f < 300 else lerp(1000, 1830, (f - 300) / 300)
        rows.append(det(f, 1, PERSON, person_at(x, 760)))
    ev = run_rules(tmp_path, rows)
    abandoned = [e for e in ev if e["type"] == "abandoned_object"]
    assert len(abandoned) == 1
    assert abandoned[0]["severity"] == pytest.approx(0.8)          # owner left the scene -> the decisive level
    assert abandoned[0]["attrs"]["owner_left_scene"] is True
    assert not [e for e in ev if e["type"] in ("custody_change", "running")]


def test_bag_carried_off_by_someone_else_is_a_custody_change(tmp_path):
    rows = []
    for f in range(0, 1800, 2):                                     # owner sits beside the bag the whole time
        rows.append(det(f, 1, PERSON, [900, 500, 1080, 800]))
    for f in range(0, 902, 2):                                      # a stranger waits far away, walks over, takes it
        if f < 450:
            x = 290
        elif f < 600:
            x = lerp(290, 1160, (f - 450) / 150)
        else:
            x = lerp(1160, 1840, (f - 600) / 300)
        rows.append(det(f, 2, PERSON, person_at(x, 750)))
        bag_x = 1110 if f < 600 else x - 50
        rows.append(det(f, 50, BACKPACK, box(bag_x, 760, 60, 60)))
    ev = run_rules(tmp_path, rows)
    custody = [e for e in ev if e["type"] == "custody_change"]
    assert len(custody) == 1
    assert custody[0]["attrs"]["owner"].endswith(":t1") and custody[0]["attrs"]["carrier"].endswith(":t2")
    assert not [e for e in ev if e["type"] == "abandoned_object"]


def test_owner_sitting_with_their_bag_raises_nothing(tmp_path):
    rows = []
    for f in range(0, 1800, 2):
        rows.append(det(f, 1, PERSON, [900, 500, 1080, 800]))
        rows.append(det(f, 50, BACKPACK, box(1110, 760, 60, 60)))
    assert run_rules(tmp_path, rows) == []


def test_walking_is_quiet_and_sprinting_is_running(tmp_path):
    walk = [det(f, 1, PERSON, person_at(lerp(200, 700, f / 600), 900, h=250)) for f in range(0, 600, 2)]
    assert run_rules(tmp_path, walk) == []                           # ~0.1 body heights per second
    sprint = [det(f, 2, PERSON, person_at(lerp(200, 1700, f / 90), 900, h=250)) for f in range(0, 90, 2)]
    ev = run_rules(tmp_path, sprint)
    assert [e["type"] for e in ev] == ["running"]
