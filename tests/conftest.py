"""Shared deterministic fixtures."""

import re

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
def normalize_cli_output():
    """Return CLI text stripped of terminal formatting and collapsed for assertions."""
    ansi_escape = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    rich_box_chars = str.maketrans("", "", "─━│┃┄┆┌┐└┘├┤┬┴┼╭╮╰╯╔╗╚╝╠╣╦╩╬")

    def normalize(output: str) -> str:
        return " ".join(ansi_escape.sub("", output).translate(rich_box_chars).split())

    return normalize


@pytest.fixture
def limiter() -> RateLimiter:
    """A no-wait limiter for deterministic tests."""
    return RateLimiter(minimum_interval=0)
