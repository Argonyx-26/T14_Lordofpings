"""Does every model load and give the right kind of answer on a known positive and a known negative?

A smoke test for the demo laptop (not an accuracy measurement: those are in data/cache/*_eval.json). Each check
loads the weights from models/, runs on real inputs and prints PASS / FAIL with the numbers it saw and the time.

Usage (from backend/):  python -m argus.eval.models_check          -> data/cache/models_check.json
"""
import json
import sys
import time
import traceback

from argus import settings

ROOT = settings.REPO_ROOT
MODELS = ROOT / "models"
RESULTS = []


def check(name: str):
    def wrap(fn):
        t0 = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        ms = round((time.perf_counter() - t0) * 1000)
        RESULTS.append({"model": name, "ok": ok, "detail": detail, "ms": ms})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<34} {ms:>6} ms  {detail}", flush=True)
        return fn
    return wrap


def frame(clip: str, second: float):
    import cv2
    cap = cv2.VideoCapture(str(settings.MEVA_DIR / "video" / f"{clip}.avi"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(second * 30))
    ok, img = cap.read()
    cap.release()
    assert ok, f"could not read {clip}"
    return img


def main() -> int:
    from ultralytics import YOLO
    bus = frame("2018-03-15.15-15-00.15-20-00.bus.G331", 200)          # the staged abandoned backpack is on the floor
    empty = frame("2018-03-15.14-50-00.14-55-00.school.G336", 1)

    @check("yolo11s  people + bags (tracking)")
    def _():
        r = YOLO(str(MODELS / "yolo11s.pt")).predict(bus, imgsz=960, conf=0.3, verbose=False)[0]
        names = [r.names[int(c)] for c in r.boxes.cls]
        return names.count("person") >= 5, f"{names.count('person')} people, {names.count('backpack')} backpacks"

    @check("yolo11m  valuables (1280, low conf)")
    def _():
        r = YOLO(str(MODELS / "yolo11m.pt")).predict(bus, imgsz=1280, conf=0.1, classes=[24, 26, 28, 63, 67],
                                                     verbose=False)[0]
        return len(r.boxes) >= 1, f"{len(r.boxes)} bags / laptops / phones"

    @check("yolo11s-pose  keypoints")
    def _():
        r = YOLO(str(MODELS / "yolo11s-pose.pt")).predict(bus, imgsz=960, conf=0.25, verbose=False)[0]
        k = r.keypoints.data if r.keypoints is not None else []
        return len(k) >= 5 and k.shape[1] == 17, f"{len(k)} people with 17 keypoints"

    from argus.vision import run_weapons, train_weapons as tw

    @check(f"weapons  {run_weapons.WEIGHTS.name}")
    def _():
        m = YOLO(str(run_weapons.WEIGHTS))
        lab = tw.OUT / "labels" / "test"
        pos = [p for p in sorted(lab.glob("*.txt")) if p.read_text().strip()][:40]
        neg = [p for p in sorted(lab.glob("*.txt")) if not p.read_text().strip()][:40]
        img = lambda p: str(tw.OUT / "images" / "test" / f"{p.stem}.jpg")           # noqa: E731
        hit = sum(len(r.boxes) > 0 for r in m.predict([img(p) for p in pos], imgsz=960, conf=0.5, verbose=False))
        fa = sum(len(r.boxes) > 0 for r in m.predict([img(p) for p in neg], imgsz=960, conf=0.5, verbose=False))
        return hit > fa, f"unseen camera: {hit}/40 weapon frames flagged, {fa}/40 clean frames flagged"

    @check("violence  pose features + random forest")
    def _():
        import joblib
        from argus.vision import violence as vio
        models = joblib.load(vio.MODEL_PATH)
        model = models.get("pose", models)["model"]
        ps = {}
        for kind, stem in (("fight", "fi001"), ("fight", "fi002"), ("no fight", "nofi001"), ("no fight", "nofi002")):
            rows = [json.loads(x) for x in (ROOT / "data/train/fights_pose" / f"{stem}.pose.jsonl").open()]
            ps[f"{kind} {stem}"] = round(float(model.predict_proba([vio.vector(vio.features(rows, 30.0))])[0, 1]), 2)
        fights = [v for k, v in ps.items() if k.startswith("fight")]
        calm = [v for k, v in ps.items() if k.startswith("no")]
        return min(fights) > max(calm) or sum(fights) > sum(calm), f"P(fight): {ps}"

    @check("VideoMAE  surveillance violence")
    def _():
        from argus.vision import violence_videomae as vm
        ps = {s: round(vm.prob(vm.read_frames(ROOT / "data/train/fights" / d / f"{s}.mp4")[:64]), 2)
              for d, s in (("fight", "fi001"), ("noFight", "nofi001"))}
        return ps["fi001"] > ps["nofi001"], f"P(violent): fight {ps['fi001']}, no fight {ps['nofi001']}"

    @check("live bag rule  (staged abandonment)")
    def _():
        from argus.vision.live_rules import LiveBagRule
        fired = []
        rule = LiveBagRule(5.0, on_event=lambda s, left, a, f: fired.append(left))
        bag, owner = [500, 400, 560, 460], [480, 250, 540, 470]
        for i in range(40):
            dets = [(24, None, 0.8, bag)] + ([(0, 1, 0.9, owner)] if i < 6 else [])
            rule.update(dets, now=i * 0.5)
        return fired == [True], f"alerts: {fired}"

    @check("Gemini  (briefs, Ask, investigator)")
    def _():
        from argus import agent
        if not agent.GEMINI_KEY:
            return False, "no GEMINI_API_KEY (the app falls back to templates and cached runs)"
        out = agent._post({"contents": [{"role": "user", "parts": [{"text": "Reply with the word ready."}]}]})
        text = out["candidates"][0]["content"]["parts"][0]["text"] if out else ""
        return "ready" in text.lower(), f"{agent.GEMINI_MODEL}: {text.strip()[:40]!r}"

    out = settings.CACHE_DIR / "models_check.json"
    out.write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "results": RESULTS}, indent=1), encoding="utf-8")
    bad = [r["model"] for r in RESULTS if not r["ok"]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} models OK" + (f"; failing: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
