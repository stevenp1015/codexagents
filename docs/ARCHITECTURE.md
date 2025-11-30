# Multi-Agent Codex Team Architecture

This document outlines the proposed architecture for a multi-agent development team built on top of the OpenAI Agents SDK while routing all model traffic through the LiteLLM proxy at `https://litellm-213047501466.us-east4.run.app/`.

## Key Concepts

- **Orchestrator Agent**: The primary agent the end user interacts with. It accepts natural-language goals, expands them into actionable workstreams, designs the required specialist agents, establishes communication cadence, and supervises execution.
- **Specialist Agents**: Dynamically instantiated by the orchestrator. Each specialist owns a slice of the overall workflow (e.g., planning, coding, testing, documentation) and proxies all hands-on execution to a dedicated Codex CLI instance.
- **Codex Bridge**: A thin wrapper around the Codex CLI MCP socket that allows agents to request actions (run commands, edit files, read context) and receive structured responses. Every specialist agent owns exactly one bridge, ensuring isolation between concurrent workstreams.
- **Team Communication Bus**: An in-memory publish/subscribe hub that allows the orchestrator and specialists to exchange updates, request help, and synchronize checkpoints at orchestrator-defined intervals.
- **Agent Registry**: Tracks the lifecycle of all agents, including their LiteLLM-backed model configuration, assigned Codex bridge, current status, and progress metrics.

## Execution Flow

1. **User Session Start**: The user opens the chat UI and greets the orchestrator.
2. **Goal Intake**: The orchestrator summarizes intent, confirms constraints, and produces a structured mission brief.
3. **Workflow Synthesis**: Using the Agents SDK, the orchestrator asks its model to emit a `TeamPlan` containing:
   - Workstream graph (tasks, dependencies, deliverables)
   - Specialist role definitions
   - Communication cadence and escalation triggers
4. **Specialist Spin-up**: For each role, the orchestrator:
   - Instantiates a LiteLLM-backed agent via the Agents SDK
   - Creates a Codex CLI bridge (unique MCP port / workspace)
   - Registers the agent and publishes an onboarding brief
5. **Parallel Execution**:
   - Specialists translate plan tasks into Codex CLI tool calls
   - Codex responses are summarized and shared on the communication bus
   - Orchestrator monitors updates, resolves blockers, reprioritizes work
6. **Checkpoints & Reviews**: At orchestrator-defined intervals, agents post status summaries. The orchestrator can trigger cross-agent reviews or pair sessions.
7. **Delivery**: Once objectives are met, the orchestrator compiles a final report and presents it to the user, including artifacts, diffs, test results, and post-mortem notes.

## Key Modules (to be implemented)

- `team/config.py`: Centralizes LiteLLM proxy location, API keys, and tuning flags.
- `team/communication.py`: Implements the in-memory pub/sub message bus with channels for status, alerts, and artifacts.
- `team/codex_bridge.py`: Wraps the Codex CLI MCP protocol (handshake, request/response framing, and session heartbeat).
- `team/agents/base.py`: Base classes for orchestrator and specialists, tying LiteLLM models to Codex bridges and the message bus.
- `team/agents/orchestrator.py`: Implements the orchestrator workflow (plan synthesis, role creation, supervision loop).
- `team/agents/specialist.py`: Implements the proxy behavior between Agents SDK function calls and Codex tool invocations.
- `team/orchestrator_app.py`: Chat-facing entry point that binds the orchestrator to a user session (CLI or GUI) and kicks off the workflow.

## Open Questions & Assumptions

- **Codex CLI MCP Details**: The exact transport for Codex CLI MCP tools is assumed to be TCP/WebSocket with JSON messages; adapters may need tweaking once confirmed.
- **Agents SDK Tooling**: The orchestrator will expose Codex actions as dynamic tools via the SDK; function signatures will mirror MCP methods (`run_command`, `apply_patch`, etc.).
- **Persistence**: Initial version keeps state in memory. Future iterations could persist plans, chat logs, and artifacts to a database for long-running programs.
- **Scalability**: Multi-process or async execution will likely be required when agents operate in parallel over long periods. The first cut uses asyncio tasks per agent.

## Next Steps

1. Bootstrap a Python package with the module skeletons listed above.
2. Implement configuration plumbing, Agents SDK wrappers, and message bus.
3. Flesh out orchestrator planning prompts and specialist execution loops.
4. Provide a demo CLI entry point for interacting with the orchestrator.
