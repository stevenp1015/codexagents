"""Adapters for talking to Codex CLI via MCP tools."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel

from .config import get_settings


class CodexError(RuntimeError):
    """Raised when a Codex CLI interaction fails."""


@dataclass
class CodexResponse:
    """Structured response wrapper for Codex CLI calls."""

    ok: bool
    data: Dict[str, Any]
    raw: str


class CodexBridge:
    """Manages a Codex CLI MCP session for a single specialist."""

    def __init__(self, agent_name: str, workspace: str) -> None:
        self.agent_name = agent_name
        self.workspace = workspace
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "CodexBridge":
        await self._start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _start(self) -> None:
        """Boot the Codex CLI process and connect pipes."""

        settings = get_settings()
        os.makedirs(self.workspace, exist_ok=True)

        cmd = [settings.codex_binary_path or "codex", "cli", "mcp"]
        env = os.environ.copy()
        env.setdefault("CODEX_AGENT_NAME", self.agent_name)

        self._process = subprocess.Popen(
            cmd,
            cwd=self.workspace,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not self._process.stdin or not self._process.stdout:
            raise CodexError("Failed to initialize Codex CLI pipes")
        loop = asyncio.get_running_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, self._process.stdout)
        self._writer = asyncio.StreamWriter(
            self._process.stdin,
            protocol,
            self._reader,
            loop,
        )

    async def close(self) -> None:
        """Terminate Codex CLI process gracefully."""

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self._process.wait), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
        self._writer = None
        self._reader = None
        self._process = None

    async def request(self, tool: str, **kwargs: Any) -> CodexResponse:
        """Send a tool invocation request to Codex."""

        if not self._writer or not self._reader:
            raise CodexError("Codex bridge is not connected")
        payload = {"tool": tool, "kwargs": kwargs}
        message = json.dumps(payload) + "\n"
        async with self._lock:
            self._writer.write(message.encode())
            await self._writer.drain()
            raw_bytes = await self._reader.readline()
        if not raw_bytes:
            raise CodexError("Codex bridge returned empty response")
        raw = raw_bytes.decode()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise CodexError(f"Invalid JSON from Codex: {raw}") from exc
        ok = bool(data.get("ok", False))
        return CodexResponse(ok=ok, data=data, raw=raw)

    async def run_command(self, command: str) -> CodexResponse:
        return await self.request("run_command", command=command)

    async def read_file(self, path: str) -> CodexResponse:
        return await self.request("read_file", path=path)

    async def apply_patch(self, path: str, patch: str) -> CodexResponse:
        return await self.request("apply_patch", path=path, patch=patch)


class CodexSessionModel(BaseModel):
    """Serialization schema for describing a Codex bridge to the Agents SDK."""

    workspace: str
    agent_name: str


__all__ = ["CodexBridge", "CodexError", "CodexResponse", "CodexSessionModel"]
