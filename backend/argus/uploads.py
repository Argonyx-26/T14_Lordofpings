"""Analyse any uploaded video with the same detector, rules and fusion as the live demo.

Pipeline per upload (one worker thread, so the GPU runs one job at a time):
  1. store the file under data/uploads/<id>/ and probe it (fps, size, length)
  2. YOLO11 + ByteTrack at ~15 analysed frames per second, then the valuables pass the demo uses
     (yolo11m at 1280 px, low confidence: bags, laptops, phones), unless ARGUS_UPLOAD_BAG_PASS=0
  3. put detections on the vision rules' clock and canvas: frame index at 30 fps (FPS in vision/common.py),
     boxes scaled to 1920x1072 (FRAME_W/H in vision/rules.py), so the rules run unchanged on any footage
  4. vision rules (ClipRules) -> CCTV events; fusion -> ranked incidents with template briefs
  5. a browser-playable MP4 for the console (ffmpeg when installed, OpenCV otherwise)

Zone-based rules (doors, walkways) need camera polygons, which an unknown clip does not have; everything
zone-free (unattended objects, objects changing hands or taken, running, crowding) runs as usual.
"""
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from argus import settings
from argus.brief.llm import template_brief
from argus.config import site
from argus.fusion.engine import FusionEngine
from argus.schema import Event

UPLOAD_DIR = settings.DATA_DIR / "uploads"
ALLOWED_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MAX_BYTES = 2 * 1024**3
ID_RE = re.compile(r"^[0-9a-f]{10}$")

ANALYSIS_FPS = 15                 # frames analysed per second of footage
CANVAS_W, CANVAS_H = 1920, 1072   # the vision rules' pixel space
FPS_CLOCK = 30.0                  # the vision rules' frame clock (FPS in vision/common.py)
CLIP_DAY = "2000-01-01"           # uploaded clips get a synthetic clock on this day ...
CLIP_START_H = 12                 # ... starting at noon, so the unknown time of day never triggers the night factor
TRACK_CLASSES = [0, 2, 3, 5, 7, 24, 26, 28, 63, 67]   # people, vehicles, bags, laptops, phones
VALUABLES = [24, 26, 28, 63, 67]
BAG_PASS = os.environ.get("ARGUS_UPLOAD_BAG_PASS", "1") != "0"
UPLOAD_AREA = "upload"


@dataclass
class Job:
    id: str
    name: str
    created: float
    status: str = "queued"        # queued | tracking | rules | done | error
    progress: float = 0.0
    message: str = "Waiting for the detector"
    meta: dict = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return UPLOAD_DIR / self.id

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "job.json").write_text(json.dumps(asdict(self)), encoding="utf-8")


def _weights(name: str = "yolo11s.pt") -> str:
    local = settings.REPO_ROOT / "models" / name
    return str(local) if local.exists() else name


def _stem(job_id: str, duration_s: float) -> str:
    """A clip name the vision rules can parse: <date>.<start>.<end>.<site>.<camera>."""
    end = timedelta(hours=CLIP_START_H, seconds=min(int(math.ceil(duration_s)), (24 - CLIP_START_H) * 3600 - 1))
    hh, rem = divmod(int(end.total_seconds()), 3600)
    mm, ss = divmod(rem, 60)
    return f"{CLIP_DAY}.{CLIP_START_H:02d}-00-00.{hh:02d}-{mm:02d}-{ss:02d}.upload.U{job_id}"


def clip_start_epoch() -> float:
    return site().local_to_epoch(f"{CLIP_DAY} {CLIP_START_H:02d}:00:00")


class UploadManager:
    def __init__(self):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        for jf in sorted(UPLOAD_DIR.glob("*/job.json")):
            try:
                job = Job(**json.loads(jf.read_text(encoding="utf-8")))
            except Exception:
                continue
            if job.status not in ("done", "error"):      # interrupted by a restart
                job.status, job.message = "error", "Interrupted by a restart; upload it again"
            self.jobs[job.id] = job
        self._queue: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="argus-uploads").start()

    # ---- intake ----------------------------------------------------------------------------
    def submit(self, stream: BinaryIO, filename: str, thorough: bool = True) -> Job:
        """thorough=False skips the valuables pass: about twice as fast, but small bags, phones and laptops
        are only seen by the main detector (good for a short clip in Q&A)."""
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError(f"Unsupported file type {suffix or '(none)'}; use {', '.join(sorted(ALLOWED_SUFFIXES))}")
        job = Job(id=uuid.uuid4().hex[:10], name=Path(filename).name[:120], created=time.time())
        job.dir.mkdir(parents=True, exist_ok=True)
        dest = job.dir / f"original{suffix}"
        written = 0
        with dest.open("wb") as f:
            while chunk := stream.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_BYTES:
                    f.close()
                    shutil.rmtree(job.dir, ignore_errors=True)
                    raise ValueError("File is larger than 2 GB")
                f.write(chunk)
        job.meta["original"] = dest.name
        job.meta["bytes"] = written
        job.meta["thorough"] = bool(thorough and BAG_PASS)
        job.save()
        self.jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id) if ID_RE.match(job_id or "") else None

    def list(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda j: -j.created)

    def result(self, job: Job) -> dict | None:
        path = job.dir / "result.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # ---- processing ------------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            job = self.jobs.get(self._queue.get())
            if job is None:
                continue
            try:
                self._process(job)
            except Exception as exc:     # a bad file must never take the server down
                traceback.print_exc()
                job.status, job.message = "error", f"{type(exc).__name__}: {exc}"
                job.save()

    def _process(self, job: Job) -> None:
        import cv2

        src = job.dir / job.meta["original"]
        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            raise ValueError("Could not open the video (unsupported codec?)")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fps = fps if 1 <= fps <= 240 else 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        cap.release()
        if not width or not height:
            raise ValueError("Could not read the video's frame size")
        duration = frames / fps if frames else 0.0
        stride = max(1, math.ceil(fps / ANALYSIS_FPS))
        stem = _stem(job.id, duration or 1)
        job.meta.update(fps=round(fps, 2), width=width, height=height, frames=frames,
                        duration_s=round(duration, 2), stride=stride, stem=stem, start_t=clip_start_epoch())
        job.status, job.message = "tracking", "Detecting and tracking objects"
        job.save()

        transcode = self._start_transcode(src, job.dir / "web.mp4")
        tracks = job.dir / f"{stem}.jsonl"
        thorough = job.meta.get("thorough", BAG_PASS)
        last = self._track(job, src, tracks, fps, width, height, frames, stride, share=0.6 if thorough else 1.0)
        if not duration:                                # container had no frame count: use what was decoded
            job.meta["duration_s"] = round((last + 1) / fps, 2)
        if thorough:
            job.message = "Looking closely for bags, laptops and phones"
            job.save()
            self._valuables(job, src, tracks.with_name(f"{stem}.bags.jsonl"), fps, width, height, frames, stride)
        self._threat_passes(job, src, tracks, fps, width, height, stride)

        job.status, job.progress, job.message = "rules", 1.0, "Applying rules and fusion"
        job.save()
        result = self._analyse(job, tracks)
        self._stills(job, src, tracks, result["events"])
        if transcode is not None:
            transcode()
        (job.dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
        n = len(result["incidents"])
        job.status = "done"
        job.message = f"{len(result['events'])} events, {n} incident{'s' if n != 1 else ''}"
        job.save()

    def _track(self, job: Job, src: Path, out: Path, fps: float, width: int, height: int, frames: int,
               stride: int, share: float) -> int:
        """Writes tracks and returns the last original frame index analysed."""
        import torch
        from ultralytics import YOLO

        model = YOLO(_weights())
        sx, sy = CANVAS_W / width, CANVAS_H / height
        tmp = out.with_suffix(".part")
        last_save = 0.0
        orig = 0
        with tmp.open("w", encoding="utf-8") as f:
            for i, r in enumerate(model.track(source=str(src), stream=True, persist=True, tracker="bytetrack.yaml",
                                              classes=TRACK_CLASSES, conf=0.25, imgsz=960,
                                              half=torch.cuda.is_available(), vid_stride=stride, verbose=False)):
                orig = i * stride
                # even frame numbers on a 30 fps clock, as if the clip were 30 fps analysed every 2nd frame
                frame = 2 * round(orig / fps * ANALYSIS_FPS)
                if r.boxes is not None and r.boxes.id is not None:
                    for box, tid, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(),
                                                 r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                        x1, y1, x2, y2 = box
                        f.write(json.dumps({"frame": frame, "tid": tid, "cls": cls, "conf": round(cf, 3),
                                            "xyxy": [round(x1 * sx, 1), round(y1 * sy, 1),
                                                     round(x2 * sx, 1), round(y2 * sy, 1)]}) + "\n")
                if frames and time.time() - last_save > 0.5:
                    job.progress = min(0.99, share * orig / frames)
                    job.save()
                    last_save = time.time()
        tmp.replace(out)
        return orig

    def _valuables(self, job: Job, src: Path, out: Path, fps: float, width: int, height: int, frames: int,
                   stride: int) -> None:
        """Same second pass as vision/run_bags.py: raw low-confidence detections the rules link themselves."""
        import torch
        from ultralytics import YOLO

        model = YOLO(_weights("yolo11m.pt"))
        sx, sy = CANVAS_W / width, CANVAS_H / height
        tmp = out.with_suffix(".part")
        last_save = 0.0
        with tmp.open("w", encoding="utf-8") as f:
            for i, r in enumerate(model.predict(source=str(src), stream=True, classes=VALUABLES, conf=0.1,
                                                imgsz=1280, half=torch.cuda.is_available(), vid_stride=stride,
                                                verbose=False)):
                orig = i * stride
                frame = 2 * round(orig / fps * ANALYSIS_FPS)
                for box, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                    x1, y1, x2, y2 = box
                    f.write(json.dumps({"frame": frame, "cls": cls, "conf": round(cf, 3),
                                        "xyxy": [round(x1 * sx, 1), round(y1 * sy, 1),
                                                 round(x2 * sx, 1), round(y2 * sy, 1)]}) + "\n")
                if frames and time.time() - last_save > 0.5:
                    job.progress = min(0.99, 0.6 + 0.4 * orig / frames)
                    job.save()
                    last_save = time.time()
        tmp.replace(out)

    def _analyse(self, job: Job, tracks: Path) -> dict:
        from argus.vision.rules import ClipRules

        raw = self._verify_weapons(job, ClipRules(tracks).run())
        events: list[Event] = []
        for n, e in enumerate(sorted(raw, key=lambda e: e["t"]), 1):
            e = {**e, "zone": UPLOAD_AREA, "area": UPLOAD_AREA}
            events.append(Event(event_id=f"up-{job.id}-{n:05d}", **e))
        return {"events": [e.model_dump() for e in events], **assess(events, None)}

    @staticmethod
    def _verify_weapons(job: Job, raw: "list[dict]") -> "list[dict]":
        """Weapon alerts get a second opinion from a vision-language model on the clip's own frame
        (vision/weapon_verify.py): on ordinary CCTV this removed 66 of 72 false alerts and kept 33 of 37 real ones."""
        if not any(e["type"] == "weapon_visible" for e in raw):
            return raw
        try:
            import cv2
            from argus.vision.common import FPS
            from argus.vision.weapon_verify import filter_events
            src = job.dir / job.meta["original"]
            fps, sx, sy = job.meta["fps"], job.meta["width"] / CANVAS_W, job.meta["height"] / CANVAS_H

            def grab(frame: int, bbox: list[float]):
                cap = cv2.VideoCapture(str(src))
                cap.set(cv2.CAP_PROP_POS_FRAMES, round(frame / FPS * fps))
                ok, img = cap.read()
                cap.release()
                return (img, [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy]) if ok else (None, None)

            job.message = "Double-checking weapon alerts"
            job.save()
            return filter_events(raw, grab)
        except Exception as exc:                   # never fail the job over the second opinion
            print(f"[uploads] weapon check skipped for {job.id}: {type(exc).__name__}: {exc}")
            return raw

    @staticmethod
    def _threat_passes(job: Job, src: Path, tracks: Path, fps: float, width: int, height: int, stride: int) -> None:
        """Pose (violence, person down, hand-offs) and weapon passes on the rules' canvas, when their models exist.
        Optional: a failure here never fails the job; the clip then simply gets no threat events."""
        from argus.vision import run_pose, run_weapons
        scale = (CANVAS_W / width, CANVAS_H / height)
        frame_scale = FPS_CLOCK / fps
        try:
            if run_pose.WEIGHTS.exists():
                job.message = "Reading body movement (fights, falls, hand-offs)"
                job.save()
                run_pose.run(src, tracks.with_name(f"{tracks.stem}.pose.jsonl"), stride=stride,
                             frame_scale=frame_scale, box_scale=scale)
                from argus.vision import violence_videomae as vm
                if vm.available():
                    job.message = "Checking for violence (pretrained video model)"
                    job.save()
                    vm.run(src, tracks.with_name(f"{tracks.stem}.pose.jsonl"),
                           tracks.with_name(f"{tracks.stem}.vmae.jsonl"), frame_scale=frame_scale, box_scale=scale)
            if run_weapons.available():
                job.message = "Looking for weapons"
                job.save()
                run_weapons.run(src, tracks.with_name(f"{tracks.stem}.weapons.jsonl"), stride=stride,
                                frame_scale=frame_scale, box_scale=scale)
        except Exception as exc:
            print(f"[uploads] threat passes skipped for {job.id}: {type(exc).__name__}: {exc}")

    @staticmethod
    def _stills(job: Job, src: Path, tracks: Path, events: "list[dict]") -> None:
        """Evidence stills (vision/thumbs.py) from the original video: the rules' canvas frame and boxes mapped
        back to the clip's own frames and pixels. Optional: a failure here never fails the job."""
        try:
            from argus.vision.common import FPS
            from argus.vision.thumbs import make_thumbs
            fps, sx, sy = job.meta["fps"], job.meta["width"] / CANVAS_W, job.meta["height"] / CANVAS_H

            def to_source(frame: int, bbox: list[float]):
                return round(frame / FPS * fps), [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy]

            make_thumbs(events, lambda _clip: src, job.dir / "thumbs", tracks_for=lambda _clip: tracks,
                        to_source=to_source)
        except Exception as exc:
            print(f"[uploads] stills skipped for {job.id}: {type(exc).__name__}: {exc}")

    @staticmethod
    def _start_transcode(src: Path, out: Path):
        """Start an H.264 MP4 encode for the browser in parallel with tracking; returns a wait() callable."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            proc = subprocess.Popen(
                [ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale='min(1280,iw)':-2",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-an",
                 "-movflags", "+faststart", str(out)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def wait():
                if proc.wait() != 0:                    # never serve a half-written file; the original is used
                    out.unlink(missing_ok=True)
            return wait

        def opencv_encode():
            import cv2
            cap = cv2.VideoCapture(str(src))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            scale = min(1.0, 1280 / max(w, 1))
            size = (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)
            writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"avc1"), fps, size)
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(cv2.resize(frame, size) if scale < 1 else frame)
            writer.release()
            cap.release()

        return opencv_encode


_manager: UploadManager | None = None
_manager_lock = threading.Lock()


def assess(events: list[Event], profile: str | None) -> dict:
    """Fuse an uploaded clip's events under a security profile (None = the site as tuned) into a threat assessment:
    ranked incidents with evidence, briefs and forecasts, the risk score over the clip, and one verdict line."""
    from argus.config import profiles
    from argus.forecast import forecast, level, risk_timeline

    cfg = site().with_profile(profile)
    engine = FusionEngine(cfg)
    for ev in events:
        engine.ingest(ev)
    incidents = engine.ranked(include_candidates=False)
    end = max((e.t for e in events), default=0.0)
    evidence, forecasts = {}, {}
    for inc in incidents:
        ev = engine.evidence(inc.incident_id)
        inc.brief = template_brief(inc, ev, cfg)
        evidence[inc.incident_id] = [e.model_dump() for e in ev]
        forecasts[inc.incident_id] = forecast(inc, ev, cfg, max(end, inc.updated_at), log=events)
    signals = [e for e in events if e.severity >= cfg.fusion["context_max_severity"]]
    titles = cfg.playbook["titles"]
    kinds: dict[str, int] = {}
    for e in signals:
        name = titles.get(e.type, e.type.replace("_", " ").capitalize())
        kinds[name] = kinds.get(name, 0) + 1
    top = max(incidents, key=lambda i: i.score, default=None)
    lvl = level(top.score, cfg) if top else ("watch" if signals else "clear")
    verdict = (f"{top.title.split(' — ')[0]}: risk {top.score}" if top else
               f"{len(signals)} signal{'s' if len(signals) != 1 else ''} noticed, none rose to an incident" if signals else
               "No threat found in this clip")
    return {
        "profile": profile, "profile_label": profiles()["profiles"][profile]["label"] if profile else "As tuned",
        "thresholds": {"watch": cfg.fusion["watch_threshold"], "open": cfg.fusion["open_threshold"]},
        "verdict": {"level": lvl, "headline": verdict, "incidents": len(incidents), "signals": len(signals),
                    "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1]))},
        "timeline": risk_timeline(events, cfg),
        "incidents": [i.model_dump() for i in incidents],
        "evidence": evidence,
        "forecasts": forecasts,
        "summary": engine.summary(),
    }


def manager() -> UploadManager:
    """One manager (and one worker) per process, even when two requests arrive at once."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = UploadManager()
    return _manager

