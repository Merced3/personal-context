"""Configuration loaded from environment variables / .env."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/context_substrate.db")
    discord_hub_url: str = Field(default="http://127.0.0.1:8000")
    discord_hub_token: str = Field(default="")

    sync_channel_ids: list[int] = Field(default_factory=list)
    sync_channel_names: dict[str, str] = Field(default_factory=dict)

    sync_messages_page_size: int = Field(default=50, ge=1, le=100)
    sync_events_page_size: int = Field(default=100, ge=1, le=500)

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

    @field_validator("sync_channel_names", mode="before")
    @classmethod
    def _parse_channel_names(cls, value: Any) -> dict[str, str]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("sync_channel_names must be a JSON object")
            return {str(k): str(v) for k, v in parsed.items()}
        raise ValueError(f"Unsupported sync_channel_names value: {value!r}")
