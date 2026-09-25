"""Ask ARGUS answers only from the log: offline it falls back to a summary, and it never passes on a citation
that is not in the log (argus/ask.py). No network: the model call is replaced."""
import argus.ask as ask_mod
from argus.config import site


def test_offline_fallback_says_nothing_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(ask_mod, "CACHE_FILE", tmp_path / "ask.json")
    monkeypatch.setenv("ARGUS_LLM", "off")
    cfg = site()
    out = ask_mod.ask("What happened at the bus station?", [], [], cfg.local_to_epoch("2018-03-15 14:55:00"), cfg)
    assert out["generated_by"] == "template"
    assert out["answer"].startswith("Nothing has been raised so far")
    assert out["cited_incidents"] == [] and out["cited_events"] == []


def test_citations_outside_the_log_are_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(ask_mod, "CACHE_FILE", tmp_path / "ask.json")
    monkeypatch.setenv("ARGUS_LLM", "on")
    monkeypatch.setattr(ask_mod, "GEMINI_KEY", "test")
    monkeypatch.setattr(ask_mod, "_gemini", lambda q, ctx: ask_mod._Answer(
        answer="A bag was taken.", cited_ids=["INC-9999", "cctv-G331-999999"]))
    cfg = site()
    out = ask_mod.ask("Anything stolen?", [], [], cfg.local_to_epoch("2018-03-15 15:00:00"), cfg)
    assert out["generated_by"] == "llm"
    assert out["cited_incidents"] == [] and out["cited_events"] == []
