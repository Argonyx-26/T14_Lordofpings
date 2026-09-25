# ARGUS: innovation audit and plan (Sat 26 Sep, 04:30 IST)

Judges' feedback: *"There is very little innovation in the current project."* This is the audit behind the response,
what we built, and why.

## 1. What already exists (read from the code, not assumed)

| Layer | What is there | Where |
|---|---|---|
| Streams | 6 MEVA CCTV cameras, door activity (annotation-derived + a video door sensor), phone GPS reduced to per-area counts; a live webcam; any uploaded clip | `ingest/`, `vision/`, `uploads.py`, `vision/live.py` |
| Detection | YOLO11 + ByteTrack, geometry rules (bag left / taken, running, occupancy), weapons (fine-tuned + VLM verifier), fights (pose + VideoMAE), person down, hand-offs, dealing | `vision/rules.py`, `vision/threats.py` |
| Fusion | Signals in one **area** within 2 min become one incident; burst damping; decisive signals; stories ("bag left + taken = possible theft") | `fusion/engine.py` |
| Score | Transparent 0-100: severity × confidence × criticality × corroboration × time × feedback | `fusion/score.py` |
| Projection | Crime-script stage, what-ifs re-scored by the real scorer, course-of-action comparison, simulate + apply | `forecast.py`, `Forecast.tsx` |
| Reasoning | Evidence-checked briefs; Ask ARGUS (cited answers from the log); a tool-using investigator agent that looks at footage | `brief/`, `ask.py`, `agent.py` |
| Human in charge | Respond menu, supervisor-only powers enforced by the API, hash-chained audit log, dismissals feed back into scoring | `api/main.py`, `audit.py` |
| Profiles | Airport / School / Park re-score the same events | `profiles.yaml` |
| UI | React 19 + Tailwind 4 + Motion, graphite design system, the ARGUS eye, camera wall, queue, to-scale site map | `frontend/src` |
| Evidence | 4/5 staged incidents, 0 false; 314 → 20 → 3; every model's score with n and method | `eval/`, `docs/MODEL_SCORES.md` |

**Strengths:** real data, measured claims, honest misses, explainable score, projection, a real agent.

**Why it still reads as "a dashboard":** every piece of intelligence is scoped to **one incident in one area**. The
engine fuses signals *within* an area and a 2-minute window, then stops. Two thefts four minutes and 250 m apart are
two unrelated rows in a list. And the system never says what it *cannot* see: the bus station has one camera and no
door sensor, the parking lots have no camera at all, yet a single-source incident there reads exactly like a
single-source incident in the school, which has four cameras and door sensors. A judge sees rows, a map and a
score: the reasoning that would make it more than a dashboard is invisible or missing.

## 2. Research: what the strongest systems do that we don't

| System | The idea that matters | Gap in ARGUS |
|---|---|---|
| [Splunk risk-based alerting](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/risk-based-alerting/risk-scoring-in-splunk-enterprise-security) | Detections don't page; they add risk to an *object*, and a risk incident rule fires when an object's accumulated risk crosses a threshold over hours | Our risk lives and dies with one incident window |
| [Microsoft Sentinel Fusion](https://learn.microsoft.com/en-us/azure/sentinel/fusion) | Correlates low-fidelity alerts across kill-chain stages and sources into one multi-stage incident | We do this inside an area; nothing links stages or incidents *across* areas |
| [OpenCTI](https://github.com/OpenCTI-Platform/opencti) / link analysis (i2, Maltego) | A knowledge graph: every fact linked to its source, with confidence, and new relations inferred from existing ones | No relation between incidents at all |
| [DeTT&CT](https://github.com/rabobank-cdc/DeTTECT) (Rabobank CDC) | Score your *visibility*: which data sources you have, their quality, and which behaviours you are blind to | ARGUS never states where it is blind |
| Near-repeat victimisation, the [Knox test](https://www.researchgate.net/publication/314293755_Comparative_Analysis_of_Two_Variants_of_the_Knox_Test_Inferences_from_Space-Time_Crime_Pattern_Analysis) and [self-exciting crime models](https://arxiv.org/pdf/1708.03579) | Crime clusters in space and time: after one theft, risk is elevated nearby for a while, then decays | Our forecast projects one incident forward, never the *site* |
| Endsley's situation awareness (already cited) | Level 3, projection | Done per incident; missing for the site |

## 3. The innovation gap and what we build

We don't add widgets. We add **one new layer of reasoning above incidents**, and make the system honest about its
own eyes. Both are computed from the data we already have, with rules anyone can read, and both are visible on the
screens the judges already look at.

| # | Feature | Problem solved | Why it is new here | Integration point | Complexity | Demo impact | Tier |
|---|---|---|---|---|---|---|---|
| 1 | **Pattern links (series)** | Two thefts 4 min and 250 m apart look unrelated | Links incidents by behaviour (same crime script, shared signals), place and time, and checks the gap is **walkable** from the site geometry. Privacy-first: it links *behaviour*, never faces or phones | new `argus/patterns.py`, `/api/intel`, incident detail, queue, site map | M | High: "three incidents are one pattern" | 1 |
| 2 | **Near-repeat watch** | After a theft, where should eyes go next? | A site-level forecast: areas reachable on foot inside the near-repeat window are marked *heightened*, with the reason and when it lapses. Checked against MEVA's staged incidents afterwards, n stated | `patterns.py`, site map | S | High: the next theft lands in a heightened area | 1 |
| 3 | **What ARGUS can see (coverage)** | A one-source incident in a one-camera area reads like a weak one | Per-area visibility from the site model (cameras, door sensors, phone coverage, recording now), shown on the map, in the score explanation ("1 of 2 streams covering the bus station agree") and in forecasts (next stage in a blind spot) | new `argus/coverage.py`, `/api/intel`, site map, "Why this score" | S-M | Medium-high: trust | 1 |
| 4 | **Case report** | After a decision, someone has to write it up | One click: what, where, when, the timeline, evidence stills, why the score, the pattern links, what ARGUS could not see, forecast, decisions and the audit hash. Printable / save as PDF | frontend `CaseReport.tsx` | S | High: closes the demo story | 1 |
| 5 | Investigator tool `related_incidents` | The agent works one case at a time | The agent can ask "is this part of a series?" | `agent.py` | S | Medium | 2 |
| 6 | Camera tamper on the live tile | A covered lens is a blind spot an attacker creates | Obstruction rule on the webcam feed raises a signal in the live area | `vision/live.py` | S | High on stage, needs the laptop | 2 |
| — | Executive mode, NL dashboard filters, 3D twin, more charts | — | Would add screens, not reasoning; the what-if simulator, response recommendations, feedback loop, copilot and replay **already exist** | — | — | — | 4 (not built) |

## 4. Architecture

```
streams ─► detect ─► fuse per area (engine) ─► score ─► brief / forecast / respond / audit        (unchanged)
                                   │
                                   ▼
                  NEW  intel layer (read-only, recomputed from engine state at the replay clock)
                       patterns.py   incident ↔ incident links: script, shared signals, gap, walkable?
                                     series (connected links) + near-repeat heightened areas
                       coverage.py   area × stream visibility, recording now, blind spots
                                   │
                                   ▼
                  GET /api/intel · snapshot["intel"] (offline demo) · console: detail, queue, map, report
```

The intel layer **never changes a score, opens or hides an incident**: evaluation numbers (4/5, 0 false) are
untouched. It adds context a person reads, and everything it says carries its basis (distance, walking time,
shared signals, window).

## 5. Demo story (3-4 minutes)

1. 14:53, school cafe: a bag is taken. The incident opens; brief, evidence, score. *(existing)*
2. The site map: the cafe incident now marks the plaza and the bus station **heightened**, "near-repeat window, 30
   min, reachable on foot in 3 min". This is ARGUS forecasting the *site*, not one incident.
3. 14:57, bus station: a suitcase taken. A second incident opens, and in its detail: **"Linked to INC-000x:
   same crime script, 250 m, walkable in the 3 min gap."** The map draws the link. The queue tags both.
4. "Why this score": the bus station has one camera and no door sensor, so the most that could agree is 2 streams.
   ARGUS says so instead of implying the evidence is weak.
5. Respond, then **Case report**: the whole story, links, blind spots and the hash-chained decision, ready to hand
   over. *(ends the loop: detect → correlate → project → decide → record)*
