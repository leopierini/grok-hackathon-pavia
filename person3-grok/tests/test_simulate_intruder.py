import asyncio
import sys
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "simulate_intruder", Path(__file__).resolve().parents[1] / "scripts" / "simulate_intruder.py"
)
sim = importlib.util.module_from_spec(_spec)
sys.modules["simulate_intruder"] = sim
_spec.loader.exec_module(sim)


def test_intruder_run_escalates_in_order():
    log = asyncio.run(sim.run())
    levels = [r["level"] for r in log]
    texts = [r["text"] for r in log]
    assert "Seeing potential intruder. Investigating." in texts
    assert "Intruder confirmed. Calling dog." in texts
    assert texts.index("Seeing potential intruder. Investigating.") < texts.index("Intruder confirmed. Calling dog.")
    assert levels.count("alert") == 1
    assert log[-1]["chip"] == "GO2" and log[-1]["action"] == "approach"
    assert [r["t"] for r in log] == sorted(r["t"] for r in log)


def test_no_dog_call_without_prior_suspicion():
    timeline = tuple(o for o in sim.TIMELINE if o.presence != "unsure")
    log = asyncio.run(sim.run(timeline))
    assert not any(r["level"] == "alert" for r in log)
    assert not any(r["chip"] == "GO2" for r in log)
