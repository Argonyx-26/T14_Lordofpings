"""Held-out evaluation: the unchanged pipeline on MEVA footage that was never used for tuning.

    python -m argus.eval.holdout                  # both windows (~22 clips, about 2 h on the RTX 5060)
    python -m argus.eval.holdout --set A          # a different day only (10 clips, ~55 min): includes 1 staged theft
    python -m argus.eval.holdout --set B          # a later window of the same day (12 clips, ~60 min)
    python -m argus.eval.holdout --set C          # another day, all six cameras + GPS (18 clips, ~90 min)
    python -m argus.eval.holdout --no-detect --set A B C   # re-score without the GPU; the report keeps every set
    python -m argus.eval.holdout --device mps     # force a device (default: whatever ultralytics picks, CUDA on the laptop)

Everything lives under data_holdout/ (gitignored), so the demo's data/ is never touched. Each step skips clips it
has already done, so the run can be stopped and resumed. The results are written to docs/HOLDOUT_RESULTS.md.

Held-out windows (all rules, zones, thresholds and fusion settings exactly as tuned on 2018-03-15 14:50-15:20):
  A  2018-03-05 13:10-13:20, a different day: G421 G419 G420 G336 G331. One staged theft (bus station, 13:18:27).
     No GPS is published for this slot, so fusion there sees cameras and doors only (a harder test).
     G331 and G336 were re-aimed between 5 and 15 March (the 15 Mar door zones land on the ceiling), so on 5 March
     they run as new cameras with no zones, exactly like an uploaded clip: no zones were drawn for the held-out view.
  B  2018-03-15 15:30-15:40, after the tuning window: all six demo cameras, with GPS. No staged theft or
     abandonment; it measures false incidents and the door sensor on unseen footage.
  C  2018-03-12 10:00-10:15, another day: all six cameras (same views as 15 Mar, checked side by side), with GPS.
     No staged theft or abandonment in the annotations; a second false-incident test on a different day.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("ARGUS_DATA", str(REPO / "data_holdout"))   # before any argus import reads settings

from argus import settings  # noqa: E402
from argus.config import site  # noqa: E402
from argus.eval.evaluate import score_window  # noqa: E402
from argus.ingest.doors import load_door_events  # noqa: E402
from argus.ingest.gps import load_device_events  # noqa: E402
from argus.schema import Event  # noqa: E402

S3 = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13"
ANN = "https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master/annotation/DIVA-phase-2/MEVA"
GPS_ZIP = "https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master/metadata/gps/gps-for-released-meva-data.zip"

WINDOWS = {
    "A": {"label": "Different day (5 Mar, 13:10-13:20)", "local": ("2018-03-05 13:10:00", "2018-03-05 13:20:00"),
          "gps": [], "moved": ["G331", "G336"], "clips": [
              "2018-03-05.13-10-00.13-15-00.school.G421", "2018-03-05.13-10-01.13-15-01.school.G419",
              "2018-03-05.13-10-01.13-15-01.school.G420", "2018-03-05.13-10-00.13-15-00.school.G336",
              "2018-03-05.13-10-01.13-15-01.bus.G331",
              "2018-03-05.13-15-00.13-20-00.school.G421", "2018-03-05.13-15-01.13-20-01.school.G419",
              "2018-03-05.13-15-01.13-20-01.school.G420", "2018-03-05.13-15-00.13-20-00.school.G336",
              "2018-03-05.13-15-01.13-20-01.bus.G331"]},
    "B": {"label": "Unseen window (15 Mar, 15:30-15:40)", "local": ("2018-03-15 15:30:00", "2018-03-15 15:40:00"),
          "gps": ["2018-03-15.15-30-00.gpx", "2018-03-15.15-35-00.gpx"], "clips": [
              "2018-03-15.15-30-00.15-35-00.school.G421", "2018-03-15.15-30-01.15-35-01.school.G419",
              "2018-03-15.15-30-01.15-35-01.school.G420", "2018-03-15.15-30-00.15-35-00.school.G638",
              "2018-03-15.15-30-00.15-35-00.school.G336", "2018-03-15.15-30-00.15-35-00.bus.G331",
              "2018-03-15.15-35-00.15-40-00.school.G421", "2018-03-15.15-35-01.15-40-01.school.G419",
              "2018-03-15.15-35-01.15-40-01.school.G420", "2018-03-15.15-35-00.15-40-00.school.G638",
              "2018-03-15.15-35-00.15-40-00.school.G336", "2018-03-15.15-35-00.15-40-00.bus.G331"]},
    "C": {"label": "Another day (12 Mar, 10:00-10:15)", "local": ("2018-03-12 10:00:00", "2018-03-12 10:15:00"),
          "gps": ["2018-03-12.10-00-00.gpx", "2018-03-12.10-05-00.gpx", "2018-03-12.10-10-00.gpx"], "clips": [
              "2018-03-12.10-00-01.10-05-01.school.G421", "2018-03-12.10-00-01.10-05-01.school.G419",
              "2018-03-12.10-00-00.10-05-00.school.G420", "2018-03-12.10-00-01.10-05-00.school.G638",
              "2018-03-12.10-00-02.10-05-02.school.G336", "2018-03-12.10-00-00.10-05-00.bus.G331",
              "2018-03-12.10-05-01.10-10-01.school.G421", "2018-03-12.10-05-01.10-10-01.school.G419",
              "2018-03-12.10-05-00.10-10-00.school.G420", "2018-03-12.10-05-01.10-10-01.school.G638",
              "2018-03-12.10-05-02.10-10-02.school.G336", "2018-03-12.10-05-00.10-10-00.bus.G331",
              "2018-03-12.10-10-01.10-15-00.school.G421", "2018-03-12.10-10-01.10-15-01.school.G419",
              "2018-03-12.10-10-00.10-15-00.school.G420", "2018-03-12.10-10-01.10-15-01.school.G638",
              "2018-03-12.10-10-02.10-15-02.school.G336", "2018-03-12.10-10-00.10-15-00.bus.G331"]},
}

ROOT = settings.DATA_DIR
VIDEO, TRACKS = ROOT / "meva" / "video", settings.TRACKS_DIR


def log(msg: str) -> None:
    print(f"[holdout {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _download(url: str, dest: Path) -> bool:
    import httpx

    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        if r.status_code != 200:
            return False
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return True


def fetch(window: str, clips: list[str]) -> None:
    for stem in clips:
        date, _, end = stem.split(".")[:3]
        hour = end[:2]
        if not _download(f"{S3}/{date}/{hour}/{stem}.r13.avi", VIDEO / f"{stem}.avi"):
            raise SystemExit(f"could not download {stem}")
        ann_dest = ROOT / "meva" / "ann" / window / f"{stem}.activities.yml"
        start_hour = stem.split(".")[1][:2]
        if not any(_download(f"{ANN}/{s}/{date}/{h}/{stem}.activities.yml", ann_dest)
                   for s in ("kitware", "kitware-meva-training") for h in dict.fromkeys((hour, start_hour))):
            log(f"no annotations for {stem} (it is still scored for false incidents)")
        log(f"have {stem}")
    gps = WINDOWS[window]["gps"]
    if gps:
        import zipfile
        zpath = ROOT / "meva" / "gps.zip"
        _download(GPS_ZIP, zpath)
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if Path(name).name in gps:
                    out = ROOT / "meva" / "gps" / window / Path(name).name
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(z.read(name))


def _unzoned_cfg(cam: str) -> dict:
    """A re-aimed camera: its site.yaml zone and area, but none of the pixel polygons drawn for the old view
    (door zones, door leaves, bag-ignore areas). The same as an uploaded clip from an unknown camera."""
    from argus.config import site as _site
    return dict(_site().camera(cam))


def detect(clips: list[str], device: str | None, moved: tuple[str, ...] = ()) -> None:
    """The demo's vision pipeline, unchanged: main pass, valuables pass, door-leaf sensor."""
    import numpy as np

    from argus.vision import door_sensor
    from argus.vision.common import camera_cfg, clip_info

    TRACKS.mkdir(parents=True, exist_ok=True)
    for stem in clips:
        clip = VIDEO / f"{stem}.avi"
        main, bags, doors = TRACKS / f"{stem}.jsonl", TRACKS / f"{stem}.bags.jsonl", TRACKS / f"{stem}.doors.npz"
        t0 = time.time()
        if not main.exists():
            _main_pass(clip, main, device)
        if not bags.exists():
            _bag_pass(clip, bags, device)
        cam = clip_info(stem).camera
        leaves = {} if cam in moved else camera_cfg(cam).get("door_leaf") or {}
        if leaves and not doors.exists():
            frames, sig = door_sensor.signals(clip, leaves)
            np.savez(doors, frames=frames, **sig)
        log(f"detected {stem} ({time.time() - t0:.0f} s)")


def _main_pass(clip: Path, out: Path, device: str | None) -> None:
    from argus.vision import run_tracks
    if device is None:                              # exactly the demo's function (CUDA + FP16 on the laptop)
        return run_tracks.run(clip, out, str(REPO / "models" / "yolo11s.pt"))
    _mirror(clip, out, device, track=True)          # same settings, another device (e.g. Apple GPU for a check)


def _bag_pass(clip: Path, out: Path, device: str | None) -> None:
    from argus.vision import run_bags
    if device is None:
        return run_bags.run(clip, out)
    _mirror(clip, out, device, track=False)


def _mirror(clip: Path, out: Path, device: str, track: bool) -> None:
    """run_tracks.run / run_bags.run with an explicit device (their settings, copied: keep in sync)."""
    from ultralytics import YOLO

    from argus.vision import run_bags, run_tracks
    stride = run_tracks.VID_STRIDE
    tmp = out.with_suffix(".part")
    with tmp.open("w", encoding="utf-8") as f:
        if track:
            model = YOLO(str(REPO / "models" / "yolo11s.pt"))
            stream = model.track(source=str(clip), stream=True, persist=True, tracker="bytetrack.yaml",
                                 classes=run_tracks.CLASSES, conf=0.3, imgsz=960, vid_stride=stride,
                                 device=device, verbose=False)
        else:
            model = YOLO(str(REPO / "models" / "yolo11m.pt"))
            stream = model.predict(source=str(clip), stream=True, classes=run_bags.BAGS, conf=0.1, imgsz=1280,
                                   vid_stride=run_bags.VID_STRIDE, device=device, verbose=False)
        for i, r in enumerate(stream):
            if track and r.boxes.id is None:
                continue
            ids = r.boxes.id.int().tolist() if track else [None] * len(r.boxes)
            for box, tid, cls, cf in zip(r.boxes.xyxy.tolist(), ids, r.boxes.cls.int().tolist(),
                                         r.boxes.conf.tolist(), strict=True):
                row = {"frame": i * stride, "cls": cls, "conf": round(cf, 3), "xyxy": [round(v, 1) for v in box]}
                if track:
                    row = {"frame": i * stride, "tid": tid, **{k: v for k, v in row.items() if k != "frame"}}
                f.write(json.dumps(row) + "\n")
    tmp.replace(out)


def camera_events(clips: list[str], moved: tuple[str, ...] = ()) -> list[Event]:
    from collections import Counter

    from argus.vision import rules
    events, counters = [], Counter()
    zoned = rules.camera_cfg
    try:
        rules.camera_cfg = lambda cam: _unzoned_cfg(cam) if cam in moved else zoned(cam)
        for stem in clips:
            for e in sorted(rules.ClipRules(TRACKS / f"{stem}.jsonl").run(), key=lambda e: e["t"]):
                counters[e["sensor_id"]] += 1
                events.append(Event(event_id=f"cctv-{e['sensor_id']}-{counters[e['sensor_id']]:06d}", **e))
    finally:
        rules.camera_cfg = zoned
    return events


def evaluate_window(window: str) -> dict:
    cfg = site()
    w = WINDOWS[window]
    start, end = (cfg.local_to_epoch(t) for t in w["local"])
    ann_dir = ROOT / "meva" / "ann" / window
    gps_dir = ROOT / "meva" / "gps" / window
    events = camera_events(w["clips"], tuple(w.get("moved", ())))
    events += load_door_events(ann_dir, cfg) if ann_dir.exists() else []
    events += load_device_events(gps_dir, cfg, start, end) if gps_dir.exists() else []
    events = [e for e in events if start <= e.t <= end]
    m = score_window(events, start, end, ann_dir, cfg)
    m["label"] = w["label"]
    m["camera_hours"] = round(len(w["clips"]) * 5 / 60, 2)
    m["streams"] = sorted({e.source for e in events})
    return m


def write_report(results: dict) -> Path:
    prev = ROOT / "results.json"
    if prev.exists():                          # keep sets scored in earlier runs; this run's sets replace theirs
        results = {**json.loads(prev.read_text(encoding="utf-8")), **results}
        results = {k: results[k] for k in sorted(results)}
    tuning = settings.REPO_ROOT / "data" / "cache" / "metrics.json"
    rows = []
    if tuning.exists():
        t = json.loads(tuning.read_text(encoding="utf-8"))
        if t.get("cctv_events"):               # without the camera events (no data/events/cctv.jsonl) it's not the result
            rows.append(("Tuning window (15 Mar, 14:50-15:20)", t, round(9 * 5 / 60, 2)))
        else:
            log("tuning-window metrics have no camera events on this machine: its row is left out")
    for key, m in results.items():
        rows.append((f"**Held-out {key}**: {m['label']}", m, m["camera_hours"]))

    def pr(d):
        return "n/a" if not d or d.get("precision") is None else f"{d['precision']:.2f} / {d['recall']:.2f}"

    lines = [
        "# Held-out results",
        "",
        "The unchanged pipeline (vision rules, zones, thresholds and fusion exactly as tuned on 15 Mar 14:50-15:20) "
        "run on MEVA footage it never saw. Produced by `python -m argus.eval.holdout`.",
        "",
        "| Window | Camera-hours | Staged incidents caught | False incidents | Raw events → incidents | "
        "Door sensor P / R (indoor) | Door P / R (all cameras) |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, m, hours in rows:
        red = m["reduction"]
        caught = f"{m['ground_truth_alerted']} / {m['ground_truth_total']}" if m["ground_truth_total"] else "none staged"
        n_false = len(m.get("false_incidents", []))
        door = m.get("door_detection", {})
        lines.append(f"| {label} | {hours} | {caught} | {n_false} | {red['raw_events']:,} → "
                     f"{red['incidents_open']} | {pr(door.get('indoor'))} | {pr(door)} |")
    lines += ["", "Notes:"]
    for key, m in results.items():
        lines.append(f"- Held-out {key} streams: {', '.join(m['streams'])}.")
        if WINDOWS[key].get("moved"):
            lines.append(f"  - Re-aimed since 15 Mar, so run with no zones (like an uploaded clip): "
                         f"{', '.join(WINDOWS[key]['moved'])}.")
        for g in m["ground_truth"]:
            lines.append(f"  - Staged {g['kind']} at {g['time']} ({g['camera']}): **{g['result']}**, "
                         f"incident score {g['peak_score']}, sources {', '.join(g['sources']) or 'none'}.")
        for fi in m.get("false_incidents", []):
            lines.append(f"  - False incident: {fi['title']} at {fi['time']} (score {fi['peak_score']}).")
    lines.append("- A larger unseen sample (20 clips from seven days, nothing staged) is in `docs/SCALE_RESULTS.md`.")
    lines.append("- Staged incidents are acted among real passers-by; MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0.")
    out = settings.REPO_ROOT / "docs" / "HOLDOUT_RESULTS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", nargs="+", choices=["A", "B", "C", "all"], default=["all"])
    ap.add_argument("--device", default=None, help="e.g. cuda:0, mps, cpu (default: ultralytics' choice)")
    ap.add_argument("--no-detect", action="store_true", help="only (re)score clips already detected")
    ap.add_argument("--only", nargs="*", help="restrict to these cameras (a quick check, e.g. --only G331)")
    args = ap.parse_args(argv)
    sets = list(WINDOWS) if "all" in args.set else list(dict.fromkeys(args.set))
    log(f"data root: {ROOT}")
    results = {}
    for key in sets:
        if args.only:
            WINDOWS[key]["clips"] = [c for c in WINDOWS[key]["clips"] if c.split(".")[-1] in args.only]
        clips = WINDOWS[key]["clips"]
        log(f"window {key}: {WINDOWS[key]['label']}, {len(clips)} clips")
        fetch(key, clips)
        if not args.no_detect:
            detect(clips, args.device, tuple(WINDOWS[key].get("moved", ())))
        results[key] = evaluate_window(key)
        m = results[key]
        log(f"window {key}: caught {m['ground_truth_alerted']}/{m['ground_truth_total']}, "
            f"false incidents {len(m['false_incidents'])}, door {m['door_detection']}")
    log(f"report: {write_report(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
