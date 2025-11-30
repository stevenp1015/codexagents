"""Orchestrator that designs the multi-agent workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..communication import Channel
from ..config import get_settings
from ..codex_bridge import CodexSessionModel
from .base import BaseAgent
from .specialist import SpecialistAgent, SpecialistSpec


@dataclass
class CommunicationRule:
    """Defines check-in cadence and recipients."""

    interval_seconds: int
    channels: List[Channel]


@dataclass
class WorkflowStep:
    """Atomic unit of work orchestrated by the team."""

    name: str
    description: str
    role: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class TeamPlan:
    """Structured plan emitted by the orchestrator model."""

    mission_brief: str
    roles: List[SpecialistSpec]
    workflow: List[WorkflowStep]
    communication: CommunicationRule

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamPlan":
        roles = [SpecialistSpec(**role) for role in data.get("roles", [])]
        workflow = [WorkflowStep(**step) for step in data.get("workflow", [])]
        comm_data = data.get("communication", {})
        channels = []
        for channel in comm_data.get("channels", [Channel.STATUS.value]):
            try:
                channels.append(Channel(channel))
            except ValueError:
                continue
        if not channels:
            channels = [Channel.STATUS]
        rule = CommunicationRule(
            interval_seconds=int(comm_data.get("interval_seconds", 300)),
            channels=channels,
        )
        return cls(
            mission_brief=data.get("mission_brief", ""),
            roles=roles,
            workflow=workflow,
            communication=rule,
        )


class OrchestratorAgent(BaseAgent):
    """High-level coordinator that spawns specialist LiteLLM agents."""

    def __init__(self, bus, agents_client=None) -> None:
        settings = get_settings()
        super().__init__(
            name="orchestrator",
            role="System Orchestrator",
            bus=bus,
            agents_client=agents_client,
        )
        self.prompt = settings.orchestrator_system_prompt
        self.plan: Optional[TeamPlan] = None
        self.specialists: Dict[str, SpecialistAgent] = {}
        self._monitors: List[asyncio.Task[None]] = []
        self._latest_status: Dict[str, Dict[str, Any]] = {}
        self._alerts: List[Dict[str, Any]] = []

    async def start(self) -> None:
        await self.boot(self.prompt)

    async def handle_user_goal(self, goal: str) -> TeamPlan:
        """Ask the orchestrator model to synthesize a plan for `goal`."""

        response = await self.send_model_message(
            content=(
                "You are designing a Codex multi-agent workflow. "
                "Return a compact JSON object with keys mission_brief, roles, workflow, communication. "
                f"User goal: {goal}"
            )
        )
        messages = response.get("messages", [])
        payload = self._extract_json(messages)
        self.plan = TeamPlan.from_dict(payload)
        await self.notify(Channel.PLAN, {"plan": payload})
        return self.plan

    async def orchestrate_goal(self, goal: str) -> TeamPlan:
        """Full orchestration pipeline for a single goal."""

        plan = await self.handle_user_goal(goal)
        await self.spin_up_specialists()
        await self.assign_workflow()
        self._ensure_supervision()
        return plan

    async def spin_up_specialists(self) -> None:
        """Instantiate specialist agents described in the plan."""

        if not self.plan:
            raise RuntimeError("Plan must exist before spinning up specialists")
        tasks = []
        for spec in self.plan.roles:
            if spec.handle in self.specialists:
                continue
            specialist = SpecialistAgent(spec=spec, bus=self.bus, orchestrator=self)
            self.specialists[spec.handle] = specialist
            tasks.append(specialist.start())
        await asyncio.gather(*tasks)

    async def assign_workflow(self) -> None:
        """Distribute workflow steps to matching specialists."""

        if not self.plan:
            raise RuntimeError("Plan must exist before assigning workflow")
        for step in self.plan.workflow:
            specialist = self.specialists.get(step.role)
            if not specialist:
                continue
            await specialist.receive_step(step)

    async def create_codex_session(self, spec: SpecialistSpec) -> CodexSessionModel:
        workspace = f"{self.settings.codex_workspace_root}/{spec.handle}"
        return CodexSessionModel(workspace=workspace, agent_name=spec.handle)

    def _ensure_supervision(self) -> None:
        if self._monitors:
            return
        self._monitors.append(asyncio.create_task(self._monitor_channel(Channel.STATUS)))
        self._monitors.append(asyncio.create_task(self._monitor_channel(Channel.ALERT)))

    async def shutdown(self) -> None:
        for task in self._monitors:
            task.cancel()
        await asyncio.gather(*self._monitors, return_exceptions=True)
        self._monitors.clear()

    async def _monitor_channel(self, channel: Channel) -> None:
        async for message in self.bus.subscribe(channel):
            if channel == Channel.STATUS:
                self._latest_status[message.sender] = message.payload
            elif channel == Channel.ALERT:
                self._alerts.append(message.payload)

    def _extract_json(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract the last JSON object from model messages."""

        for message in reversed(messages):
            for item in message.get("content", []):
                if item.get("type") == "output_text":
                    text = item.get("text", "")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        continue
        raise ValueError("No JSON payload found in orchestrator response")


__all__ = ["TeamPlan", "OrchestratorAgent"]
