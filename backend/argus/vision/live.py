"""LIVE INFERENCE tile: real-time YOLO11 + ByteTrack on one camera, served as MJPEG.

  python backend/argus/vision/live.py                         # loops G421 cafe clip at real time
  python backend/argus/vision/live.py --source 0              # laptop webcam
  python backend/argus/vision/live.py --clip <stem> --port 8001

Frontend: <img src="http://localhost:8001/live.mjpg">   stats: GET http://localhost:8001/live/stats
Nothing else depends on this process; if it misbehaves on stage, just stop it.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import threading
import time
from collections import Counter, deque

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ultralytics import YOLO

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.vision.common import MEVA_DIR, camera_cfg, clip_info  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
CLASSES = [0, 2, 3, 5, 7, 24, 26, 28]
NAMES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 24: "backpack", 26: "handbag", 28: "suitcase"}
COLORS = {0: (80, 200, 255), 24: (0, 200, 255), 26: (0, 200, 255), 28: (0, 200, 255)}
OUT_W = 960
ATTRIBUTION = "MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0"


def no_power_throttling() -> None:
    """Windows 11 power-throttles (EcoQoS) processes without a foreground window, and run_demo.ps1 starts
    this one minimized: that alone halves the fps. Opt this process out. No-op elsewhere."""
    if sys.platform != "win32":
        return
    import ctypes

    class State(ctypes.Structure):
        _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]

    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    s = State(1, 1, 0)  # version 1, control EXECUTION_SPEED, state off -> never throttle
    k32.SetProcessInformation(ctypes.c_void_p(k32.GetCurrentProcess()), 4, ctypes.byref(s), ctypes.sizeof(s))  # 4 = ProcessPowerThrottling


class Live:
    def __init__(self, source, label: str, polygons: dict, weights: str, imgsz: int, header: bool = False):
        self.source, self.label, self.polygons, self.header = source, label, polygons, header
        self.model = YOLO(weights)
        self.imgsz = imgsz
        self.jpeg: bytes | None = None
        self.cond = threading.Condition()
        self.stats = {"fps": 0.0, "infer_ms": 0.0, "counts": {}, "frame": 0, "source": str(label), "running": False}
        self.stop = False

    def draw(self, img, r, fps, infer_ms):
        h, w = img.shape[:2]
        s = OUT_W / w
        img = cv2.resize(img, (OUT_W, int(h * s)))
        for name, pts in self.polygons.items():
            p = (np.array(pts) * s).astype(np.int32)
            cv2.polylines(img, [p], True, (255, 160, 60), 1, cv2.LINE_AA)
        counts = Counter()
        if r.boxes is not None and len(r.boxes):
            ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(r.boxes)
            for box, cls, cf, tid in zip(r.boxes.xyxy.tolist(), r.boxes.cls.int().tolist(), r.boxes.conf.tolist(), ids):
                counts[NAMES.get(cls, str(cls))] += 1
                x1, y1, x2, y2 = (int(v * s) for v in box)
                col = COLORS.get(cls, (120, 255, 120))
                cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
                tag = f"{NAMES.get(cls, cls)}{'' if tid is None else f' #{tid}'} {cf:.2f}"
                cv2.putText(img, tag, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)
        if self.header:  # standalone use; the console draws its own header from /live/stats
            self._header(img, fps, infer_ms)
        cv2.putText(img, ATTRIBUTION, (8, img.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (230, 230, 230), 1, cv2.LINE_AA)
        return img, counts

    def _header(self, img, fps, infer_ms):
        cv2.rectangle(img, (0, 0), (OUT_W, 26), (20, 20, 20), -1)
        cv2.circle(img, (14, 13), 6, (0, 0, 255), -1)
        cv2.putText(img, f"LIVE INFERENCE  YOLO11 + ByteTrack  {fps:4.1f} fps  {infer_ms:4.1f} ms/frame  |  {self.label}",
                    (28, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    def run(self):
        while not self.stop:
            cap = cv2.VideoCapture(self.source)
            src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
            period = 1.0 / min(src_fps, 30)
            times: deque = deque(maxlen=30)
            self.stats["running"] = True
            n = 0
            while not self.stop:
                t0 = time.perf_counter()
                ok, frame = cap.read()
                if not ok:
                    break  # end of clip -> loop
                t1 = time.perf_counter()
                r = self.model.track(frame, persist=True, tracker="bytetrack.yaml", classes=CLASSES, conf=0.3,
                                     imgsz=self.imgsz, half=True, verbose=False)[0]
                infer_ms = (time.perf_counter() - t1) * 1000
                times.append(time.perf_counter())
                fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
                img, counts = self.draw(frame, r, fps, infer_ms)
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                with self.cond:
                    self.jpeg = buf.tobytes()
                    self.cond.notify_all()
                n += 1
                self.stats.update(fps=round(fps, 1), infer_ms=round(infer_ms, 1), counts=dict(counts), frame=n)
                if isinstance(self.source, str):  # file: pace to real time; webcam paces itself
                    dt = time.perf_counter() - t0
                    if dt < period:
                        time.sleep(period - dt)
            cap.release()
            self.model.predictor.trackers[0].reset() if getattr(self.model, "predictor", None) and \
                getattr(self.model.predictor, "trackers", None) else None


def make_app(live: Live) -> FastAPI:
    app = FastAPI(title="ARGUS live inference")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def frames():
        last = None
        while True:
            with live.cond:
                live.cond.wait_for(lambda: live.jpeg is not None and live.jpeg is not last, timeout=2.0)
                jpg = live.jpeg
            if jpg is None or jpg is last:
                continue
            last = jpg
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"

    @app.get("/live.mjpg")
    def mjpg():
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/live/stats")
    def stats():
        return live.stats

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default="2018-03-15.14-50-00.14-55-00.school.G421")
    ap.add_argument("--source", help="webcam index (e.g. 0) or a video path; overrides --clip")
    ap.add_argument("--weights", default=str(ROOT / "models" / "yolo11s.pt"))
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--header", action="store_true", help="burn an fps/latency header into the stream (standalone use)")
    a = ap.parse_args()
    no_power_throttling()
    if a.source is not None:
        src = int(a.source) if a.source.isdigit() else a.source
        label, polys = (f"webcam {src}" if isinstance(src, int) else pathlib.Path(src).stem), {}
    else:
        src = str(MEVA_DIR / "video" / f"{a.clip}.avi")
        cam = clip_info(a.clip).camera
        cfg = camera_cfg(cam)
        label, polys = f"{cam} {cfg.get('label', '')}", cfg.get("polygons") or {}
    live = Live(src, label, polys, a.weights, a.imgsz, header=a.header)
    threading.Thread(target=live.run, daemon=True).start()
    uvicorn.run(make_app(live), host="127.0.0.1", port=a.port, log_level="warning")
