"""Specialist agents that proxy Codex CLI execution."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..codex_bridge import CodexBridge, CodexSessionModel
from ..communication import Channel
from .base import BaseAgent

if TYPE_CHECKING:  # pragma: no cover - type only
    from .orchestrator import OrchestratorAgent, WorkflowStep


@dataclass
class SpecialistSpec:
    """Describes a dynamically created specialist role."""

    handle: str
    display_name: str
    mission: str
    instructions: str
    check_in_seconds: int = 300
    capabilities: List[str] = field(default_factory=list)


class SpecialistAgent(BaseAgent):
    """Bridges between the Agents SDK model and Codex CLI operations."""

    def __init__(
        self,
        spec: SpecialistSpec,
        bus,
        orchestrator: "OrchestratorAgent",
    ) -> None:
        super().__init__(
            name=spec.handle,
            role=spec.display_name,
            bus=bus,
            agents_client=orchestrator.agents_client,
        )
        self.spec = spec
        self.orchestrator = orchestrator
        self.codex_session: Optional[CodexSessionModel] = None
        self._task_queue: asyncio.Queue["WorkflowStep"] = asyncio.Queue()
        self._runner: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        self.codex_session = await self.orchestrator.create_codex_session(self.spec)
        await self.boot(self._instructions)
        await self.notify(Channel.STATUS, {"event": "specialist_boot", "handle": self.spec.handle})
        self._runner = asyncio.create_task(self._loop())




    @property
    def _instructions(self) -> str:
        session = self.codex_session
        codex_info = (
            f"Codex workspace: {session.workspace} (agent: {session.agent_name})." if session else "Codex session pending."
        )
        capabilities = ", ".join(self.spec.capabilities or ["planning", "execution"])
        return (
            f"Role: {self.spec.display_name}\n"
            f"Mission: {self.spec.mission}\n"
            f"Codex: {codex_info}\n"
            f"Check-ins every {self.spec.check_in_seconds} seconds.\n"
            f"Capabilities: {capabilities}\n"
            'When you produce actions, respond with JSON using the schema {"actions": [{"tool": str, "arguments": dict}]}.'
        )

    async def receive_step(self, step: "WorkflowStep") -> None:
        await self._task_queue.put(step)

    async def _loop(self) -> None:
        while True:
            step = await self._task_queue.get()
            try:
                await self._execute_step(step)
            except Exception as exc:  # pragma: no cover - defensive
                await self.notify(
                    Channel.ALERT,
                    {
                        "event": "specialist_error",
                        "handle": self.spec.handle,
                        "step": step.name,
                        "error": str(exc),
                    },
                )

    async def _execute_step(self, step: "WorkflowStep") -> None:
        await self.notify(
            Channel.STATUS,
            {
                "event": "step_start",
                "handle": self.spec.handle,
                "step": step.name,
                "description": step.description,
            },
        )
        prompt = (
            f"Task: {step.description}\n"
            f"Dependencies: {', '.join(step.depends_on) if step.depends_on else 'none'}\n"
            "Respond with JSON specifying Codex actions to take."
        )
        response = await self.send_model_message(prompt, metadata={"step": step.name})
        actions = self._parse_actions(response)
        session = self.codex_session or await self.orchestrator.create_codex_session(self.spec)
        async with CodexBridge(agent_name=session.agent_name, workspace=session.workspace) as bridge:
            for action in actions:
                tool = action.get("tool")
                kwargs = action.get("arguments", {})
                result = await self._dispatch_tool(bridge, tool, kwargs)
                await self.notify(
                    Channel.ARTIFACT,
                    {
                        "event": "codex_action",
                        "handle": self.spec.handle,
                        "step": step.name,
                        "tool": tool,
                        "result": result.data,
                    },
                )
        await self.notify(
            Channel.STATUS,
            {
                "event": "step_complete",
                "handle": self.spec.handle,
                "step": step.name,
            },
        )

    def _parse_actions(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = response.get("messages", [])
        for message in reversed(messages):
            for item in message.get("content", []):
                if item.get("type") == "output_text":
                    try:
                        data = json.loads(item.get("text", ""))
                    except json.JSONDecodeError:
                        continue
                    actions = data.get("actions")
                    if isinstance(actions, list):
                        return actions
        return []

    async def _dispatch_tool(self, bridge: CodexBridge, tool: str, kwargs: Dict[str, Any]) -> Any:
        if tool == "run_command":
            return await bridge.run_command(kwargs.get("command", ""))
        if tool == "read_file":
            return await bridge.read_file(kwargs.get("path", ""))
        if tool == "apply_patch":
            return await bridge.apply_patch(kwargs.get("path", ""), kwargs.get("patch", ""))
        raise ValueError(f"Unknown tool requested by specialist: {tool}")


__all__ = ["SpecialistAgent", "SpecialistSpec"]
