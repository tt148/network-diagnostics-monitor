"""Latency and packet-loss diagnostics with ping-to-TCP fallback."""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import time
from itertools import pairwise
from statistics import mean
from typing import Any

from ..config import Settings
from ..safety import RateLimiter, resolve_host_safely, validate_live_target


def _summary(samples: list[float], attempted: int, method: str) -> dict[str, Any]:
    """Calculate latency statistics and packet loss from successful samples.

    ``samples`` must be in probe order: jitter is the mean absolute difference
    between consecutive probes, which sorting the samples would hide.
    """
    successes = len(samples)
    if samples:
        minimum = round(min(samples), 2)
        maximum = round(max(samples), 2)
        average = round(mean(samples), 2)
        jitter = (
            round(mean(abs(b - a) for a, b in pairwise(samples)), 2) if len(samples) > 1 else 0.0
        )
    else:
        minimum = maximum = average = jitter = None
    loss = round((attempted - successes) / attempted * 100, 2) if attempted else 0.0
    return {
        "method": method,
        "probes_sent": attempted,
        "probes_received": successes,
        "packet_loss_percent": loss,
        "min_ms": minimum,
        "avg_ms": average,
        "max_ms": maximum,
        "jitter_ms": jitter,
    }


_PING_UNAVAILABLE_HINTS = ("operation not permitted", "permission denied", "not permitted")


def _ping_once(ping_args: list[str], timeout: float) -> tuple[str, float | None]:
    """Run one ping and classify the outcome.

    Returns ``("ok", ms)``, ``("lost", None)`` when ping ran but got no reply, or
    ``("unavailable", None)`` when ICMP cannot be used here (no ``ping`` binary or
    no permission), in which case the caller may fall back to a TCP probe.
    """
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            ping_args,
            capture_output=True,
            text=True,
            timeout=timeout + 1,
            check=False,
        )
    except FileNotFoundError:
        return "unavailable", None
    except subprocess.TimeoutExpired:
        return "lost", None
    output = f"{completed.stdout}{completed.stderr}"
    if completed.returncode == 0:
        match = re.search(r"time[=<]\s*([\d.]+)\s*ms", output, flags=re.IGNORECASE)
        elapsed = float(match.group(1)) if match else (time.perf_counter() - started) * 1000
        return "ok", elapsed
    if any(hint in output.lower() for hint in _PING_UNAVAILABLE_HINTS):
        return "unavailable", None
    return "lost", None


def _tcp_once(hostname: str, timeout: float) -> float | None:
    """Time one TCP connection to port 443; return None when it fails."""
    started = time.perf_counter()
    try:
        with socket.create_connection((hostname, 443), timeout=timeout):
            return (time.perf_counter() - started) * 1000
    except OSError:
        return None


def check_latency(
    target: str,
    *,
    mode: str = "simulated",
    settings: Settings | None = None,
    count: int = 3,
    limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Measure a small number of latency probes; no scan or parallel probes."""
    if not 1 <= count <= 5:
        raise ValueError("count must be between 1 and 5 to keep probes bounded.")
    settings = settings or Settings()
    if mode == "simulated":
        return {
            "target": target,
            "mode": "simulated",
            "status": "ok",
            **_summary([18.0, 19.2, 18.7][:count], count, "simulated"),
            "message": "SIMULATED: no ping or TCP connection was attempted.",
        }
    if mode != "live":
        raise ValueError("mode must be 'simulated' or 'live'")

    hostname = validate_live_target(target, settings)
    resolve_host_safely(hostname, settings, settings.timeout_seconds)
    limiter = limiter or RateLimiter(settings.min_check_interval_seconds)
    samples: list[float] = []
    methods_used: set[str] = set()
    system = platform.system().lower()
    ping_args = ["ping", "-n" if system == "windows" else "-c", "1"]
    if system == "windows":
        ping_args += ["-w", str(int(settings.timeout_seconds * 1000))]
    else:
        ping_args += ["-W", str(max(1, int(settings.timeout_seconds)))]
    ping_args.append(hostname)

    for _ in range(count):
        limiter.wait_turn()
        outcome, elapsed = _ping_once(ping_args, settings.timeout_seconds)
        if outcome == "unavailable":
            # ICMP is not usable here (for example a container without NET_RAW),
            # so measure TCP connect time instead.
            methods_used.add("tcp-connect-fallback")
            elapsed = _tcp_once(hostname, settings.timeout_seconds)
        else:
            methods_used.add("ping")
        # A ping that ran but got no reply is real packet loss; it must not be
        # hidden by retrying over TCP.
        if elapsed is not None:
            samples.append(elapsed)

    if methods_used == {"ping", "tcp-connect-fallback"}:
        method = "mixed"
    else:
        method = next(iter(methods_used))
    summary = _summary(samples, count, method)
    return {
        "target": hostname,
        "mode": "live",
        "status": "unreachable"
        if not samples
        else ("degraded" if summary["packet_loss_percent"] > 0 else "ok"),
        **summary,
        "message": "Live latency result; probes were sequential and bounded.",
    }
