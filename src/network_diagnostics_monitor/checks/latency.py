"""Latency and packet-loss diagnostics with ping-to-TCP fallback."""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import time
from statistics import mean
from typing import Any

from ..config import Settings
from ..safety import RateLimiter, SafetyError, resolve_host_safely, validate_live_target


def _summary(samples: list[float], attempted: int, method: str) -> dict[str, Any]:
    """Calculate latency statistics and packet loss from successful samples."""
    successes = len(samples)
    ordered = sorted(samples)
    if ordered:
        minimum = round(ordered[0], 2)
        maximum = round(ordered[-1], 2)
        average = round(mean(ordered), 2)
        jitter = round(mean(abs(b - a) for a, b in zip(ordered, ordered[1:])), 2) if len(ordered) > 1 else 0.0
    else:
        minimum = maximum = average = jitter = None
    return {
        "method": method,
        "probes_sent": attempted,
        "probes_received": successes,
        "packet_loss_percent": round((attempted - successes) / attempted * 100, 2) if attempted else 0.0,
        "min_ms": minimum,
        "avg_ms": average,
        "max_ms": maximum,
        "jitter_ms": jitter,
    }


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
    method = "ping"
    system = platform.system().lower()
    ping_args = ["ping", "-n" if system == "windows" else "-c", "1"]
    if system == "windows":
        ping_args += ["-w", str(int(settings.timeout_seconds * 1000))]
    else:
        ping_args += ["-W", str(max(1, int(settings.timeout_seconds)))]
    ping_args.append(hostname)

    for _ in range(count):
        limiter.wait_turn()
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                ping_args,
                capture_output=True,
                text=True,
                timeout=settings.timeout_seconds + 1,
                check=False,
            )
            output = completed.stdout + completed.stderr
            match = re.search(r"time[=<]\s*([\d.]+)\s*ms", output, flags=re.IGNORECASE)
            if completed.returncode == 0:
                samples.append(float(match.group(1)) if match else (time.perf_counter() - started) * 1000)
                continue
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        method = "tcp-connect-fallback"
        try:
            started = time.perf_counter()
            with socket.create_connection((hostname, 443), timeout=settings.timeout_seconds):
                samples.append((time.perf_counter() - started) * 1000)
        except OSError:
            continue

    summary = _summary(samples, count, method)
    return {
        "target": hostname,
        "mode": "live",
        "status": "unreachable" if not samples else ("degraded" if summary["packet_loss_percent"] > 0 else "ok"),
        **summary,
        "message": "Live latency result; probes were sequential and bounded.",
    }
