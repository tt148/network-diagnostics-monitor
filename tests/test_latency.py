"""Latency checker tests are deterministic and network-free."""

import pytest

from network_diagnostics_monitor.checks.latency import _summary, check_latency


def test_simulated_latency_summary(settings) -> None:
    result = check_latency("example.com", settings=settings, count=3)
    assert result["mode"] == "simulated"
    assert result["probes_sent"] == 3
    assert result["probes_received"] == 3
    assert result["packet_loss_percent"] == 0
    assert result["min_ms"] <= result["avg_ms"] <= result["max_ms"]


def test_probe_count_is_bounded(settings) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        check_latency("example.com", settings=settings, count=6)


def test_summary_handles_total_loss() -> None:
    result = _summary([], 2, "test")
    assert result["packet_loss_percent"] == 100
    assert result["avg_ms"] is None
    assert result["jitter_ms"] is None


def test_live_latency_rejects_non_allowlisted_target(settings) -> None:
    with pytest.raises(ValueError, match="not in NDM_ALLOWED_TARGETS"):
        check_latency("not-allowed.invalid", mode="live", settings=settings)


def test_live_latency_uses_ping_and_returns_statistics(monkeypatch, settings, limiter) -> None:
    import subprocess
    import network_diagnostics_monitor.checks.latency as latency

    monkeypatch.setattr(latency, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"])
    monkeypatch.setattr(
        latency.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="time=12.5 ms", stderr=""),
    )
    result = check_latency("example.com", mode="live", settings=settings, count=2, limiter=limiter)
    assert result["mode"] == "live"
    assert result["method"] == "ping"
    assert result["probes_received"] == 2
    assert result["avg_ms"] == 12.5


def test_live_latency_falls_back_to_tcp(monkeypatch, settings, limiter) -> None:
    import subprocess
    import network_diagnostics_monitor.checks.latency as latency

    class FakeSocket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr(latency, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"])
    monkeypatch.setattr(latency.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(latency.socket, "create_connection", lambda *args, **kwargs: FakeSocket())
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["method"] == "tcp-connect-fallback"
    assert result["probes_received"] == 1


def test_live_latency_total_failure(monkeypatch, settings, limiter) -> None:
    import network_diagnostics_monitor.checks.latency as latency

    monkeypatch.setattr(latency, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"])
    monkeypatch.setattr(latency.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(latency.socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["status"] == "unreachable"
    assert result["packet_loss_percent"] == 100
