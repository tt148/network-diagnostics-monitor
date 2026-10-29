"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings; simulated mode is deliberately the default."""

    model_config = SettingsConfigDict(
        env_prefix="NDM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: Literal["simulated", "live"] = "simulated"
    allowed_targets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "example.com",
            "localhost",
            "127.0.0.1",
            "cloudflare-dns.com",
            "1.1.1.1",
        ]
    )
    allow_lab_ranges: bool = False
    min_check_interval_seconds: float = Field(default=2.0, ge=0.0, le=3600.0)
    timeout_seconds: float = Field(default=3.0, gt=0.0, le=30.0)
    slow_dns_threshold_ms: float = Field(default=500.0, ge=0.0)
    allow_live_api: bool = False
    api_key: str | None = None
    dns_resolvers: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["1.1.1.1", "8.8.8.8"]
    )

    @field_validator("allowed_targets", "dns_resolvers", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        """Accept comma-separated environment variables or normal lists."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("allowed_targets")
    @classmethod
    def normalize_targets(cls, value: list[str]) -> list[str]:
        """Normalize hostnames without silently accepting empty entries."""
        return [target.rstrip(".").lower() for target in value]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for application use."""
    return Settings()
