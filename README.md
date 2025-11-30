# Codex Multi-Agent Team

Experimental orchestration layer that uses the OpenAI Agents SDK with LiteLLM-backed models to coordinate a hierarchy of Codex CLI-powered development agents.

## Features

- Orchestrator agent that chats with the user and synthesizes team workflows
- Dynamically provisioned specialist agents that own Codex CLI bridges
- Internal publish/subscribe bus for cross-agent communication
- Configurable check-in cadence, escalation paths, and role templates
- Typer-based CLI entry point for launching interactive sessions

> ⚠️ **Status**: Early scaffolding. Networking endpoints, authentication, and Codex CLI protocol details must be configured before use.

## Getting Started

1. Create and activate a Python 3.10+ environment.
2. Install dependencies:

   ```bash
   pip install -e .[dev]
   ```

3. Export configuration for the LiteLLM proxy (or place them in a `.env` file):

   ```bash
   export CODEX_TEAM_LITELLM_API_KEY="your-proxy-key"
   export CODEX_TEAM_LITELLM_MODEL="gpt-4.1-mini"
   export CODEX_TEAM_CODEX_BINARY_PATH="/path/to/codex"
   ```

4. Launch the orchestrator planning CLI:

   ```bash
   python -m codex_team.orchestrator_app --goal "Refactor the authentication module"
   ```

   The orchestrator will provision itself via the LiteLLM-backed Agents SDK, synthesize a team plan, spin up specialists, and publish events to the in-memory bus.

## Configuration

Key environment variables (all prefixed with `CODEX_TEAM_`):

- `LITELLM_BASE_URL`: LiteLLM proxy endpoint (defaults to the provided Cloud Run URL)
- `LITELLM_API_KEY`: LiteLLM proxy credential
- `LITELLM_MODEL`: Default model name exposed by the proxy
- `LITELLM_CUSTOM_PROVIDER`: Optional provider hint passed as `custom_llm_provider` when creating assistants
- `CODEX_BINARY_PATH`: Absolute path to the Codex CLI executable (required)
- `CODEX_WORKSPACE_ROOT`: Directory where per-agent sandboxes are created
- `DEFAULT_CHECK_IN_SECONDS`: Fallback cadence for specialist status reports

See `src/codex_team/config.py` for the authoritative list.

## Next Steps

- Flesh out MCP request/response framing once the Codex CLI protocol is finalized
- Replace the simple JSON prompting with structured tool execution callbacks
- Persist orchestration logs and plans for auditability
- Surface the communication bus via WebSocket so the GUI can reflect live updates
