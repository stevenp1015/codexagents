"""Lightweight in-memory pub/sub bus for cross-agent communication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Set


class Channel(str, Enum):
    """Named channels for message routing."""

    STATUS = "status"
    ALERT = "alert"
    PLAN = "plan"
    ARTIFACT = "artifact"
    HEARTBEAT = "heartbeat"


@dataclass
class Message:
    """Represents a payload published on the bus."""

    channel: Channel
    sender: str
    payload: Dict[str, Any]


class PubSubBus:
    """Async publish/subscribe message bus."""

    def __init__(self) -> None:
        self._subscribers: Dict[Channel, Set[asyncio.Queue[Message]]] = {
            channel: set() for channel in Channel
        }
        self._lock = asyncio.Lock()

    async def publish(self, message: Message) -> None:
        """Publish `message` to all channel subscribers."""

        async with self._lock:
            queues = list(self._subscribers.get(message.channel, set()))
        for queue in queues:
            await queue.put(message)

    async def subscribe(self, channel: Channel) -> AsyncIterator[Message]:
        """Yield messages for subscribers to `channel`. Caller must consume messages."""

        queue: asyncio.Queue[Message] = asyncio.Queue()
        async with self._lock:
            self._subscribers[channel].add(queue)
        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            async with self._lock:
                self._subscribers[channel].discard(queue)

    async def snapshot(self, channel: Channel) -> List[Message]:
        """Return current queued messages for inspection (non-destructive)."""

        async with self._lock:
            queues = list(self._subscribers.get(channel, set()))
        messages: List[Message] = []
        for queue in queues:
            messages.extend(list(queue._queue))  # type: ignore[attr-defined]
        return messages


__all__ = ["Channel", "Message", "PubSubBus"]
