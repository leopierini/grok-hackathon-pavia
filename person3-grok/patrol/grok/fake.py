"""Scripted reasoner. Fake mode does not call xAI or open a socket."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from patrol.contract import (
    DispatchDecision,
    Frame,
    GroundDecision,
    Incident,
    Resolution,
    RunContext,
)
from patrol.grok.presence import PRESENCE_PROMPT_VERSION, presence_state


class FakeReasoner:
    """Four v1 decisions plus a presence read, both scripted by scenario name."""

    def __init__(self, config: Mapping[str, object], output_dir: Path) -> None:
        self.config = dict(config)
        self.output_dir = output_dir
        self.trace: list[str] = []

    def metadata(self) -> Mapping[str, str]:
        model = self.config.get("model", "fake")
        prompt = self.config.get("prompt_version", "patrol-v1")
        return {
            "model": str(model),
            "prompt_version": str(prompt),
            "presence_prompt_version": PRESENCE_PROMPT_VERSION,
            "sdk_version": "simulated",
        }

    def read_presence(self, scenario: str) -> str:
        self.trace.append(f"presence:{scenario}")
        return presence_state(scenario)

    async def assess_incident(self, incident: Incident, ctx: RunContext) -> DispatchDecision:
        del incident, ctx
        self.trace.append("assess_incident")
        scenario = str(self.config.get("scenario", "blocked_resolved"))
        if scenario == "dismiss":
            return DispatchDecision("dismiss", "Scripted dismiss.")
        if scenario == "invalid_model":
            from patrol.contract import AdapterError

            raise AdapterError("api_error", "scripted invalid model output")
        return DispatchDecision("dispatch", "Scripted dispatch.")

    async def assess_ground_view(
        self, incident: Incident, frame: Frame, ctx: RunContext
    ) -> GroundDecision:
        del incident, frame, ctx
        self.trace.append("assess_ground_view")
        scenario = str(self.config.get("scenario", "blocked_resolved"))
        if scenario == "ground_clear":
            return GroundDecision("sufficient", "Clear ground view.", "Scripted clear.")
        return GroundDecision("inspect", "Blocked ground view.", "Scripted inspect.")

    async def resolve_incident(
        self,
        incident: Incident,
        ground: Frame,
        aerial: Frame | None,
        ctx: RunContext,
    ) -> Resolution:
        del incident, ground, aerial, ctx
        self.trace.append("resolve_incident")
        scenario = str(self.config.get("scenario", "blocked_resolved"))
        if scenario == "ground_clear":
            return Resolution("cleared", "Nothing left in frame.", "Scripted cleared.")
        return Resolution("confirmed", "Target still there.", "Scripted confirmed.")

    async def compose_alert(
        self, incident: Incident, result: Resolution, ctx: RunContext
    ) -> str:
        del ctx
        self.trace.append("compose_alert")
        return f"{incident.zone}: {result.outcome}. {result.summary}"

    async def close(self) -> None:
        self.trace.append("close")
