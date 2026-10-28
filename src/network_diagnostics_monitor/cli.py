"""Typer command-line interface."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from .checks.dns import check_dns
from .checks.http import check_http
from .checks.latency import check_latency
from .config import Settings, get_settings
from .safety import RateLimiter, SafetyError

app = typer.Typer(
    name="network-diagnostics",
    help="Safe, simulated-first network diagnostics.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Keep subcommands explicit, including the diagnose command."""


@app.command()
def diagnose(
    target: Annotated[str, typer.Argument(help="Hostname, IP, or HTTP(S) URL.")],
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="simulated (default) or live (allowlist required)."),
    ] = None,
) -> None:
    """Run DNS, latency, and HTTP/TLS checks for one target."""
    settings: Settings = get_settings()
    selected_mode = mode or settings.mode
    if selected_mode not in {"simulated", "live"}:
        raise typer.BadParameter("mode must be 'simulated' or 'live'")
    limiter = RateLimiter(settings.min_check_interval_seconds)
    try:
        result = {
            "target": target,
            "mode": selected_mode,
            "dns": check_dns(target, mode=selected_mode, settings=settings, limiter=limiter),
            "latency": check_latency(target, mode=selected_mode, settings=settings, limiter=limiter),
            "http": check_http(target, mode=selected_mode, settings=settings, limiter=limiter),
        }
    except (SafetyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
