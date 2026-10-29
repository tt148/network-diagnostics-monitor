"""Latency checker tests are deterministic and network-free."""

import subprocess

import pytest

import network_diagnostics_monitor.checks.latency as latency
from network_diagnostics_monitor.checks.latency import _summary, check_latency


class FakeSocket:
    """Minimal context manager standing in for a connected TCP socket."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _raise(exc: BaseException):
    def _inner(*args, **kwargs):
        raise exc

    return _inner


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    def _inner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], returncode, stdout=stdout, stderr=stderr)

    return _inner


@pytest.fixture
def safe_resolution(monkeypatch):
    """Skip real DNS resolution; the target resolves to a public documentation address."""
    monkeypatch.setattr(latency, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"])


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


def test_summary_jitter_follows_probe_order() -> None:
    # Consecutive differences are |30-10| = 20 and |20-30| = 10, so jitter is 15.
    # Sorting the samples first would incorrectly report 10.
    result = _summary([10.0, 30.0, 20.0], 3, "test")
    assert result["jitter_ms"] == 15.0
    assert result["min_ms"] == 10.0
    assert result["max_ms"] == 30.0
    assert result["avg_ms"] == 20.0


def test_summary_reports_partial_loss() -> None:
    result = _summary([12.0], 4, "test")
    assert result["packet_loss_percent"] == 75
    assert result["jitter_ms"] == 0.0


def test_live_latency_rejects_non_allowlisted_target(settings) -> None:
    with pytest.raises(ValueError, match="not in NDM_ALLOWED_TARGETS"):
        check_latency("not-allowed.invalid", mode="live", settings=settings)


def test_live_latency_uses_ping_and_returns_statistics(
    monkeypatch, settings, limiter, safe_resolution
) -> None:
    monkeypatch.setattr(latency.subprocess, "run", _completed(0, stdout="time=12.5 ms"))
    result = check_latency("example.com", mode="live", settings=settings, count=2, limiter=limiter)
    assert result["mode"] == "live"
    assert result["method"] == "ping"
    assert result["probes_received"] == 2
    assert result["avg_ms"] == 12.5


def test_live_latency_falls_back_to_tcp_when_ping_is_missing(
    monkeypatch, settings, limiter, safe_resolution
) -> None:
    monkeypatch.setattr(latency.subprocess, "run", _raise(FileNotFoundError()))
    monkeypatch.setattr(latency.socket, "create_connection", lambda *args, **kwargs: FakeSocket())
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["method"] == "tcp-connect-fallback"
    assert result["probes_received"] == 1


def test_live_latency_falls_back_to_tcp_when_icmp_is_not_permitted(
    monkeypatch, settings, limiter, safe_resolution
) -> None:
    monkeypatch.setattr(
        latency.subprocess,
        "run",
        _completed(2, stderr="ping: socket: Operation not permitted"),
    )
    monkeypatch.setattr(latency.socket, "create_connection", lambda *args, **kwargs: FakeSocket())
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["method"] == "tcp-connect-fallback"
    assert result["probes_received"] == 1


def test_ping_loss_is_not_hidden_by_tcp_fallback(
    monkeypatch, settings, limiter, safe_resolution
) -> None:
    monkeypatch.setattr(latency.subprocess, "run", _completed(1, stdout="Request timed out."))
    monkeypatch.setattr(
        latency.socket,
        "create_connection",
        _raise(AssertionError("TCP must not be used when ping ran but received no reply")),
    )
    result = check_latency("example.com", mode="live", settings=settings, count=2, limiter=limiter)
    assert result["method"] == "ping"
    assert result["status"] == "unreachable"
    assert result["packet_loss_percent"] == 100


def test_ping_timeout_counts_as_packet_loss(monkeypatch, settings, limiter, safe_resolution) -> None:
    monkeypatch.setattr(
        latency.subprocess, "run", _raise(subprocess.TimeoutExpired(cmd="ping", timeout=1))
    )
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["method"] == "ping"
    assert result["packet_loss_percent"] == 100


def test_live_latency_total_failure(monkeypatch, settings, limiter, safe_resolution) -> None:
    monkeypatch.setattr(latency.subprocess, "run", _raise(FileNotFoundError()))
    monkeypatch.setattr(latency.socket, "create_connection", _raise(OSError("offline")))
    result = check_latency("example.com", mode="live", settings=settings, count=1, limiter=limiter)
    assert result["status"] == "unreachable"
    assert result["packet_loss_percent"] == 100
