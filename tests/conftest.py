"""Shared deterministic fixtures."""

import pytest

from network_diagnostics_monitor.config import Settings
from network_diagnostics_monitor.safety import RateLimiter


@pytest.fixture
def settings() -> Settings:
    """Settings with a small, explicit allowlist for unit tests."""
    return Settings(
        _env_file=None,
        allowed_targets=["example.com", "localhost", "127.0.0.1", "cloudflare-dns.com", "1.1.1.1"],
        min_check_interval_seconds=0,
        timeout_seconds=0.1,
    )


@pytest.fixture
def limiter() -> RateLimiter:
    """A no-wait limiter for deterministic tests."""
    return RateLimiter(minimum_interval=0)
