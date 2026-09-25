"""The live unattended-bag rule on scripted detections (cls, track id, conf, xyxy), one frame per 0.5 s."""
from argus.vision.live_rules import LiveBagRule

BAG = [500, 400, 560, 460]


def person(x):
    return [x, 250, x + 60, 470]


def run(frames, abandon_s=5.0):
    fired = []
    rule = LiveBagRule(abandon_s, on_event=lambda s, owner_left, alone_s, frame: fired.append((s.kind, owner_left, t)))
    for i, dets in enumerate(frames):
        t = i * 0.5
        rule.update(dets, now=t)
    return fired


def test_owner_leaves_bag_fires_once():
    carry = [[(0, 1, 0.9, person(480)), (24, None, 0.8, BAG)]] * 6          # arrives with its owner, rests
    gone = [[(24, None, 0.8, BAG)]] * 20                                      # owner walks out of frame
    fired = run(carry + gone)
    assert len(fired) == 1
    kind, owner_left, t = fired[0]
    assert kind == "backpack" and owner_left and 5.0 <= t - 3.0 <= 6.0


def test_owner_stays_no_alert():
    assert run([[(0, 1, 0.9, person(480)), (24, None, 0.8, BAG)]] * 40) == []


def test_bystander_does_not_attend_someone_elses_bag():
    carry = [[(0, 1, 0.9, person(480)), (24, None, 0.8, BAG)]] * 6
    crowd = [[(0, 2, 0.9, person(490)), (24, None, 0.8, BAG)]] * 20          # a stranger stands by it
    assert len(run(carry + crowd)) == 1


def test_owner_returning_resets_the_countdown():
    carry = [[(0, 1, 0.9, person(480)), (24, None, 0.8, BAG)]] * 6
    away = [[(24, None, 0.8, BAG)]] * 6                                       # 3 s away: under the 5 s limit
    assert run(carry + away + carry + away) == []


def test_knife_in_hand_fires_once_knife_on_table_does_not():
    from argus.vision.live_rules import LiveSharpRule
    fired = []
    rule = LiveSharpRule(on_event=lambda etype, attrs, box, sev, conf, frame: fired.append((etype, attrs["weapon"])))
    hand = [(0, 1, 0.9, [100, 100, 200, 400]), (43, None, 0.6, [190, 200, 230, 260])]    # touching the person
    table = [(0, 1, 0.9, [100, 100, 200, 400]), (43, None, 0.6, [600, 300, 650, 330])]   # far from anyone
    for i in range(30):
        rule.update(table, now=i * 0.1)
    assert fired == []
    for i in range(30, 60):
        rule.update(hand, now=i * 0.1)
    assert fired == [("weapon_visible", "knife")]                # once, then the 20 s refractory


# ---- camera tamper ------------------------------------------------------------------------------------------
def _scene(seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)
    img = np.full((360, 640, 3), 110, np.uint8)
    for _ in range(60):                                   # a scene with edges: boxes of different greys
        x, y = int(rng.integers(0, 600)), int(rng.integers(0, 330))
        img[y:y + 30, x:x + 40] = int(rng.integers(20, 240))
    return img


def _tamper(frames, dt=0.1):
    from argus.vision.live_rules import LiveTamperRule
    fired = []
    rule = LiveTamperRule(on_event=lambda etype, attrs, box, sev, conf, frame: fired.append((etype, attrs, sev)))
    for i, f in enumerate(frames):
        rule.update(f, now=i * dt)
    return fired, rule


def test_covering_the_lens_for_two_seconds_fires_once_and_restores():
    import numpy as np
    scene = [_scene()] * 20
    covered = [np.full((360, 640, 3), 40, np.uint8)] * 30         # a hand over the lens: flat and dim, 3 s
    fired, rule = _tamper(scene + covered + scene)
    assert [f[0] for f in fired] == ["camera_obstructed", "camera_restored"]
    assert fired[0][1]["reason"].startswith("lens covered") and fired[0][2] >= 0.6
    assert 2.5 <= fired[1][1]["view_lost_s"] <= 3.5 and not rule.obstructed


def test_a_hand_passing_the_lens_is_not_tampering():
    import numpy as np
    fired, _ = _tamper([_scene()] * 20 + [np.zeros((360, 640, 3), np.uint8)] * 10 + [_scene()] * 20)   # 1 s
    assert fired == []


def test_a_smeared_lens_fires_against_the_scenes_own_detail():
    import cv2
    scene = _scene()
    smeared = cv2.GaussianBlur(scene, (0, 0), 25)
    fired, _ = _tamper([scene] * 20 + [smeared] * 30)
    assert fired and fired[0][0] == "camera_obstructed" and "smeared" in fired[0][1]["reason"]
