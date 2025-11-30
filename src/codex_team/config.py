"""Runtime configuration for the Codex multi-agent team."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration with sane defaults.

    Values can be overridden via env vars prefixed with `CODEX_TEAM_`.
    """

    litellm_base_url: HttpUrl = Field(
        default="https://litellm-213047501466.us-east4.run.app/",
        description="LiteLLM proxy endpoint"
    )
    litellm_api_key: str = Field(
        default="dummy-key",
        description="API key for LiteLLM proxy"
    )
    litellm_model: str = Field(
        default="gpt-4.1-mini",
        description="Default model identifier exposed by the proxy"
    )
    litellm_custom_provider: Optional[str] = Field(
        default="openai",
        description="Optional LiteLLM custom_llm_provider override"
    )
    orchestrator_system_prompt: str = Field(
        default=(
            "You are the orchestrator of a Codex CLI development team. Gather "
            "requirements, design workflows, spawn specialists protected by "
            "LiteLLM-backed models, and deliver results with clear reports."
        ),
        description="High-level instructions for the orchestrator agent"
    )
    default_check_in_seconds: int = Field(
        default=300,
        description="Fallback cadence for specialist status reports"
    )
    codex_binary_path: Optional[str] = Field(
        default=None,
        description="Optional path to the Codex CLI executable"
    )
    codex_workspace_root: str = Field(
        default="./workspaces",
        description="Root directory where specialist workspaces will be created"
    )

    class Config:
        env_prefix = "CODEX_TEAM_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Singleton accessor for settings."""

    return Settings()


__all__ = ["Settings", "get_settings"]
