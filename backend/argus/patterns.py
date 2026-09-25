"""Pattern links: the layer above incidents. Two thefts four minutes and 150 m apart are not two unrelated rows.

The fusion engine joins signals that share one area and a two-minute window. This module looks across incidents:

- links     incident -> later incident, when both follow the same offender script (playbook `scripts`, e.g. theft),
            share the act itself (a `link_stages` stage: a bag taken, not merely a bag left) and the gap between them
            is inside the near-repeat window. Walking time between the areas (site geometry and the site's own
            walking assumptions) says what kind of link it is: `repeat` (same place), `near_repeat` (walkable: one
            person could have done both) or `concurrent` (too soon to walk: two people, or a coordinated pair).
- series    connected links, oldest first: "3 bag thefts in 24 min across the school cafe and the bus station".
- watch     near-repeat watch for the site: after an offender-script incident, crime clusters in space and time
            (near-repeat victimisation), so every area is ranked by criticality x nearness (walking time) x how
            recent the last incident is, with the camera that can see it, or a note that none can.

Nothing here identifies a person: links are made from behaviour, place and time only. Nothing here changes a score,
opens or hides an incident; it is context for the operator, with its basis stated on every line.
"""
import math

from argus.config import SiteConfig
from argus.forecast import _area_centre, _metres, match_script, source_of
from argus.schema import Event, Incident

LINKABLE = ("watch", "open", "ack", "escalated")


def settings_of(cfg: SiteConfig) -> dict:
    p = cfg.playbook.get("patterns") or {}
    return {"scripts": p.get("scripts", ["theft", "assault", "dealing"]), "window_s": p.get("window_s", 1800),
            "walk_slack_s": p.get("walk_slack_s", 30), "nouns": p.get("nouns", {}),
            "watch_decay_walk_s": p.get("watch_decay_walk_s", 180),
            "link_stages": p.get("link_stages", {})}


def walk_s(a: str, b: str, cfg: SiteConfig) -> tuple[int | None, int | None]:
    """(metres along a walking path, seconds on foot) between two areas' centres, from the site's own assumptions."""
    if a == b:
        return 0, 0
    ca, cb = _area_centre(a, cfg), _area_centre(b, cfg)
    if ca is None or cb is None:
        return None, None
    r = cfg.raw.get("response", {})
    d = _metres(ca, cb) * r.get("path_factor", 1.3)
    return round(d), round(d / r.get("walk_mps", 1.4))


def signature(inc: Incident, evidence: list[Event], cfg: SiteConfig) -> dict | None:
    """The incident's behaviour: which offender script it follows and which of its stages it reached. Only what a
    camera saw counts as behaviour: phone counts alone (people gathering) never make an incident part of a series."""
    types = [t for t in (list(dict.fromkeys(e.type for e in evidence)) or inc.signal_types) if source_of(t) == "cctv"]
    script = match_script(types, cfg) if types else None
    if not script or script["id"] not in settings_of(cfg)["scripts"]:
        return None
    stages = [script["stages"][i]["id"] for i in script["reached"]]
    acts = [e for e in evidence if e.type in types and any(e.type in st["types"] for st in script["stages"])]
    return {"script": script["id"], "script_name": script["name"], "stages": stages,
            "labels": {st["id"]: st["label"] for st in script["stages"]},
            "types": [t for t in types if any(t in st["types"] for st in script["stages"])],
            # the behaviour's own time span: when the camera saw the script's signals, not when phones joined in
            "start": min((e.t for e in acts), default=inc.first_signal_at),
            "end": max((e.t for e in acts), default=inc.updated_at)}


def links(incidents: list[Incident], evidence_of, cfg: SiteConfig, now: float) -> tuple[list[dict], dict[str, dict]]:
    """Every pair of incidents that plausibly belong together, with the reason, oldest pair first."""
    s = settings_of(cfg)
    sigs = {}
    for inc in incidents:
        if inc.status not in LINKABLE or inc.first_signal_at > now:
            continue
        sig = signature(inc, [e for e in evidence_of(inc.incident_id) if e.t <= now], cfg)
        if sig:
            sigs[inc.incident_id] = (inc, sig)
    order = sorted(sigs.values(), key=lambda p: p[1]["start"])
    out = []
    for i, (a, sa) in enumerate(order):
        for b, sb in order[i + 1:]:
            if sa["script"] != sb["script"]:
                continue
            shared = [st for st in sa["stages"] if st in sb["stages"]]
            acts = s["link_stages"].get(sa["script"])
            if not shared or (acts and not set(shared) & set(acts)):
                continue                       # they must share the act itself, not only a precursor (a bag left)
            gap = sb["start"] - sa["end"]
            if gap > s["window_s"]:
                continue
            metres, walk = walk_s(a.area, b.area, cfg)
            if a.area == b.area:
                kind = "repeat"
            elif walk is not None and gap < walk - s["walk_slack_s"]:
                kind = "concurrent"            # too soon for one person to walk it: two people, or a coordinated pair
            else:
                kind = "near_repeat"
            union = list(dict.fromkeys(sa["stages"] + sb["stages"]))
            out.append({
                "from": a.incident_id, "to": b.incident_id, "kind": kind, "script": sa["script"],
                "script_name": sa["script_name"], "from_area": a.area, "to_area": b.area,
                "gap_s": round(gap), "distance_m": metres, "walk_s": walk,
                "shared_stages": [sa["labels"][st] for st in shared],
                "shared_types": [t for t in sa["types"] if t in sb["types"]],
                "similarity": round(len(shared) / len(union), 2),
                "why": _why(kind, a, b, gap, metres, walk, [sa["labels"][st] for st in shared], cfg),
            })
    return out, {k: v[1] for k, v in sigs.items()}


def _why(kind, a, b, gap, metres, walk, shared, cfg) -> str:
    stage = ", then ".join(st[0].lower() + st[1:] for st in shared)
    if kind == "concurrent":
        when = "at the same time" if gap <= 0 else f"{_mins(gap)} apart, too soon to walk the {metres} m ({_mins(walk)})"
        return (f"Same behaviour ({stage}) in {cfg.area_name(a.area)} and {cfg.area_name(b.area)} {when}: "
                "two people, or a coordinated pair")
    if kind == "repeat":
        return f"Same behaviour ({stage}) in the same place {_mins(gap)} later"
    return (f"Same behaviour ({stage}) {_mins(gap)} later, {metres} m away: walkable in {_mins(walk)}")


def _mins(s: float | None) -> str:
    if s is None:
        return "an unknown time"
    s = max(0, round(s))
    return f"{s // 60}:{s % 60:02d}"


def series(link_list: list[dict], sigs: dict[str, dict], incidents: dict[str, Incident], cfg: SiteConfig) -> list[dict]:
    """Connected links as series, oldest first. A series is a pattern, not a verdict: the same behaviour, walkable."""
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for ln in link_list:
        parent[find(ln["from"])] = find(ln["to"])
    groups: dict[str, list[str]] = {}
    for iid in parent:
        groups.setdefault(find(iid), []).append(iid)
    nouns = settings_of(cfg)["nouns"]
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda i: sigs[i]["start"])
        script = sigs[members[0]]["script"]
        areas = list(dict.fromkeys(incidents[i].area for i in members))
        start, end = sigs[members[0]]["start"], max(sigs[i]["end"] for i in members)
        own = [ln for ln in link_list if ln["from"] in members]
        noun = nouns.get(script, sigs[members[0]]["script_name"].lower())
        where = " and ".join(cfg.area_name(a) for a in areas) if len(areas) <= 2 else f"{len(areas)} areas"
        out.append({
            "series_id": f"S-{members[0].split('-')[-1]}", "script": script, "script_name": sigs[members[0]]["script_name"],
            "incidents": members, "areas": areas, "start": start, "end": end, "span_s": round(end - start),
            "title": f"{len(members)} {noun} in {math.ceil((end - start) / 60)} min" + (f" across {where}" if len(areas) > 1 else f" in {where}"),
            "concurrent": any(ln["kind"] == "concurrent" for ln in own),
            "reading": _reading(own),
        })
    return sorted(out, key=lambda s: s["start"])


def _reading(own: list[dict]) -> str:
    """What the links allow one to conclude, and no more."""
    fast = [ln for ln in own if ln["kind"] == "concurrent"]
    tail = " ARGUS links behaviour, place and time; it never identifies people."
    if fast:
        pair = fast[0]
        return (f"At least two people: {pair['from']} and {pair['to']} were too close in time for one person to do both. "
                "A crew working the site is a working hypothesis, not a finding." + tail)
    return "Every gap could be walked: one offender or one crew is a working hypothesis, not a finding." + tail


def watch(sigs: dict[str, dict], incidents: dict[str, Incident], cfg: SiteConfig, now: float,
          seen_by: dict[str, list[str]]) -> dict | None:
    """Near-repeat watch: where to look next after an offender-script incident, while its window is open."""
    s = settings_of(cfg)
    def did_act(sig):
        acts = s["link_stages"].get(sig["script"])
        return not acts or bool(set(sig["stages"]) & set(acts))
    recent = [(iid, sig) for iid, sig in sigs.items() if did_act(sig) and 0 <= now - sig["end"] <= s["window_s"]]
    if not recent:
        return None
    iid, sig = max(recent, key=lambda p: p[1]["end"])
    origin = incidents[iid].area
    left = s["window_s"] - (now - sig["end"])
    fresh = left / s["window_s"]
    areas = []
    for area in cfg.area_shapes:
        metres, walk = walk_s(origin, area, cfg)
        if walk is None:
            continue
        near = math.exp(-walk / s["watch_decay_walk_s"])
        weight = cfg.criticality(area) * near * fresh
        cams = seen_by.get(area, [])
        areas.append({"area": area, "walk_s": walk, "distance_m": metres, "criticality": cfg.criticality(area),
                      "weight": round(weight, 3), "cameras": cams, "blind": not cams,
                      "why": ("where it happened" if area == origin else f"{_mins(walk)} on foot") +
                             f" · criticality {cfg.criticality(area):.1f}" + ("" if cams else " · no camera sees it")})
    areas.sort(key=lambda a: -a["weight"])
    for i, a in enumerate(areas):
        a["rank"] = i + 1
        a["heightened"] = i < 2 and a["weight"] > 0
    reachable = max((a["walk_s"] for a in areas), default=0)
    return {"after": iid, "script": sig["script"], "origin": origin, "since": sig["end"], "until": sig["end"] + s["window_s"],
            "remaining_s": int(left), "areas": areas,
            "site_walk_s": reachable,
            "basis": (f"Offences like this cluster in space and time (near-repeat). The whole site is within "
                      f"{_mins(reachable)} on foot, so for {s['window_s'] // 60} min after {iid} every area is in reach; "
                      "areas are ranked by criticality, nearness and how recent it was. A prompt for attention, not a prediction of a crime."),
            }


def intel_patterns(incidents: list[Incident], evidence_of, cfg: SiteConfig, now: float, seen_by: dict[str, list[str]]) -> dict:
    by_id = {i.incident_id: i for i in incidents}
    link_list, sigs = links(incidents, evidence_of, cfg, now)
    return {"links": link_list, "series": series(link_list, sigs, by_id, cfg), "watch": watch(sigs, by_id, cfg, now, seen_by)}
