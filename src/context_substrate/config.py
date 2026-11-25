"""Configuration loaded from environment variables / .env."""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/context_substrate.db")
    discord_hub_url: str = Field(default="http://127.0.0.1:8000")
    discord_hub_token: str = Field(default="")

    sync_channel_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    sync_channel_names: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    sync_messages_page_size: int = Field(default=50, ge=1, le=100)
    sync_events_page_size: int = Field(default=100, ge=1, le=500)

    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8010, ge=1, le=65535)
    consumer_tokens: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    sync_interval_seconds: int = Field(default=300, ge=5)
    harness_data_dir: str = Field(default="./data/harness")
    harness_database_url: str | None = Field(default=None)

    search_semantic_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("sync_channel_ids", mode="before")
    @classmethod
    def _parse_channel_ids(cls, value: Any) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return [int(v) for v in json.loads(stripped)]
            return [int(part.strip()) for part in stripped.split(",") if part.strip()]
        raise ValueError(f"Unsupported sync_channel_ids value: {value!r}")

    @field_validator("sync_channel_names", "consumer_tokens", mode="before")
    @classmethod
    def _parse_str_dict(cls, value: Any) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("Expected a JSON object")
            return {str(k): str(v) for k, v in parsed.items()}
        raise ValueError(f"Unsupported dict value: {value!r}")
