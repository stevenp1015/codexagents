"""Shared abstractions for orchestrator and specialist agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..communication import Channel, Message, PubSubBus
from ..config import Settings, get_settings


@dataclass
class AgentDescriptor:
    """Metadata describing an instantiated agent."""

    assistant_id: str
    thread_id: str
    name: str
    role: str


class AgentsClient:
    """Wrapper around the OpenAI Agents SDK for LiteLLM-backed models."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.client = OpenAI(
            base_url=str(self.settings.litellm_base_url),
            api_key=self.settings.litellm_api_key,
        )

    async def create_agent(self, name: str, instructions: str, tools: Optional[List[Dict[str, Any]]] = None) -> AgentDescriptor:
        """Create an agent and a fresh thread for it."""

        def _create() -> AgentDescriptor:
            payload = {
                "model": self.settings.litellm_model,
                "name": name,
                "instructions": instructions,
                "tools": tools or [],
            }
            if self.settings.litellm_custom_provider:
                payload["extra_body"] = {"custom_llm_provider": self.settings.litellm_custom_provider}
            assistant = self.client.beta.assistants.create(**payload)
            thread = self.client.beta.threads.create()
            return AgentDescriptor(
                assistant_id=assistant.id,
                thread_id=thread.id,
                name=name,
                role=instructions.split("\n", 1)[0][:64],
            )

        return await asyncio.to_thread(_create)

    async def send_message(self, descriptor: AgentDescriptor, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a message to the agent's thread and collect the response."""

        def _send() -> Dict[str, Any]:
            self.client.beta.threads.messages.create(
                thread_id=descriptor.thread_id,
                role="user",
                content=content,
                metadata=metadata,
            )
            run = self.client.beta.threads.runs.create(
                thread_id=descriptor.thread_id,
                assistant_id=descriptor.assistant_id,
            )
            while True:
                status = self.client.beta.threads.runs.retrieve(
                    thread_id=descriptor.thread_id,
                    run_id=run.id,
                )
                if status.status in {"completed", "failed", "cancelled"}:
                    break
            messages = self.client.beta.threads.messages.list(thread_id=descriptor.thread_id)
            return {
                "run_status": status.status,
                "messages": [m.model_dump() for m in messages.data],
            }

        return await asyncio.to_thread(_send)


class BaseAgent:
    """Base functionality shared by orchestrator and specialists."""

    def __init__(
        self,
        name: str,
        role: str,
        bus: PubSubBus,
        agents_client: Optional[AgentsClient] = None,
    ) -> None:
        self.name = name
        self.role = role
        self.bus = bus
        self.settings = get_settings()
        self.agents_client = agents_client or AgentsClient(self.settings)
        self.descriptor: Optional[AgentDescriptor] = None
        self._lock = asyncio.Lock()

    async def boot(self, instructions: str, tools: Optional[List[Dict[str, Any]]] = None) -> None:
        """Provision the underlying Agents SDK representation."""

        async with self._lock:
            if self.descriptor is None:
                self.descriptor = await self.agents_client.create_agent(
                    name=self.name,
                    instructions=instructions,
                    tools=tools,
                )

    async def notify(self, channel: Channel, payload: Dict[str, Any]) -> None:
        """Publish a message onto the shared bus."""

        await self.bus.publish(Message(channel=channel, sender=self.name, payload=payload))

    async def send_model_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Relay a user message to the Agents SDK model and fetch its response."""

        if not self.descriptor:
            raise RuntimeError(f"Agent {self.name} is not booted")
        return await self.agents_client.send_message(self.descriptor, content, metadata)


__all__ = ["AgentsClient", "AgentDescriptor", "BaseAgent"]
