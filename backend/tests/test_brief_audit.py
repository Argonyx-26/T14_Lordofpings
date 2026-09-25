from argus.audit import AuditLog
from argus.brief.llm import _LLMBrief, brief_for, template_brief, validate
from argus.fusion.engine import FusionEngine
from tests.test_fusion import T0, ev


def _incident(cfg):
    eng = FusionEngine(cfg)
    eng.ingest(ev(1, "cctv", "custody_change", 0.45, 0.5))
    eng.ingest(ev(2, "device", "device_crowding", 0.44, t=T0 + 30))
    inc = next(iter(eng.incidents.values()))
    return inc, eng.evidence(inc.incident_id)


def test_template_brief_is_valid(cfg):
    inc, evidence = _incident(cfg)
    b = template_brief(inc, evidence, cfg)
    assert b.action_id in cfg.playbook["actions"]
    assert set(b.evidence_ids) <= set(inc.event_ids)
    assert b.generated_by == "template"


def test_validator_rejects_invented_action_evidence_or_place(cfg):
    inc, _ = _incident(cfg)
    good = _LLMBrief(summary="Object changed hands at the bus station.", why="Two sources agree.",
                     action_id="track_subject", evidence_ids=["t-1", "t-2"])
    assert validate(good, inc, cfg).generated_by == "llm"
    assert validate(good.model_copy(update={"action_id": "shoot_first"}), inc, cfg) is None
    assert validate(good.model_copy(update={"evidence_ids": ["t-1", "made-up"]}), inc, cfg) is None
    assert validate(good.model_copy(update={"summary": "Theft in the School building."}), inc, cfg) is None


def test_brief_falls_back_to_template_when_llm_off(cfg):
    inc, evidence = _incident(cfg)
    assert brief_for(inc, evidence, cfg).generated_by == "template"


def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.append(incident_id="INC-0001", action="ack", role="duty_officer")
    log.append(incident_id="INC-0001", action="escalate", role="supervisor")
    assert log.verify()
    lines = log.path.read_text().splitlines()
    lines[0] = lines[0].replace("duty_officer", "supervisor")
    log.path.write_text("\n".join(lines) + "\n")
    assert not log.verify()
