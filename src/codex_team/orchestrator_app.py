"""CLI entry point for interacting with the orchestrator."""

from __future__ import annotations

import asyncio
from pprint import pprint

import typer

from .agents.orchestrator import OrchestratorAgent
from .communication import PubSubBus

app = typer.Typer(add_completion=False)


@app.command()
def plan(goal: str = typer.Option(..., prompt=True, help="High-level objective for the orchestrator")) -> None:
    """Generate a multi-agent plan for `goal` and display the result."""

    async def _run() -> None:
        bus = PubSubBus()
        orchestrator = OrchestratorAgent(bus=bus)
        await orchestrator.start()
        team_plan = await orchestrator.handle_user_goal(goal)
        pprint(team_plan)

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover - CLI
    app()
