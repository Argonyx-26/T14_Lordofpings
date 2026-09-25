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
