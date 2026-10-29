"""Safety boundary tests; no network is used."""

import pytest

from network_diagnostics_monitor.safety import (
    RateLimiter,
    SafetyError,
    hostname_from_target,
    validate_live_target,
    validate_resolved_addresses,
)


def test_hostname_from_url_and_hostname() -> None:
    assert hostname_from_target("https://Example.com/path") == "example.com"
    assert hostname_from_target("Example.com.") == "example.com"


def test_rejects_invalid_url_shape() -> None:
    with pytest.raises(SafetyError):
        hostname_from_target("ftp://example.com")
    with pytest.raises(SafetyError):
        hostname_from_target("example.com/path")


def test_allowlisted_public_target(settings) -> None:
    assert validate_live_target("example.com", settings) == "example.com"
    assert validate_live_target("1.1.1.1", settings) == "1.1.1.1"


def test_rejects_target_outside_allowlist(settings) -> None:
    with pytest.raises(SafetyError, match="not in NDM_ALLOWED_TARGETS"):
        validate_live_target("google.com", settings)


@pytest.mark.parametrize("address", ["10.0.0.1", "192.168.1.2", "169.254.169.254", "100.100.100.200"])
def test_blocks_private_link_local_and_metadata_ips(address, settings) -> None:
    settings.allowed_targets.append(address)
    with pytest.raises(SafetyError):
        validate_live_target(address, settings)


def test_loopback_requires_explicit_allowlist(settings) -> None:
    settings.allowed_targets.remove("127.0.0.1")
    with pytest.raises(SafetyError):
        validate_live_target("127.0.0.1", settings)


def test_resolved_private_ip_is_rejected(settings) -> None:
    with pytest.raises(SafetyError):
        validate_resolved_addresses(["192.168.1.5"], settings)


@pytest.mark.parametrize("address", ["::ffff:10.0.0.1", "::ffff:169.254.169.254"])
def test_blocks_ipv4_mapped_private_literals(address, settings) -> None:
    settings.allowed_targets.append(address)
    with pytest.raises(SafetyError):
        validate_live_target(address, settings)


def test_resolved_ipv4_mapped_private_ip_is_rejected(settings) -> None:
    with pytest.raises(SafetyError, match="blocked"):
        validate_resolved_addresses(["::ffff:10.0.0.1"], settings, "example.com")


def test_resolved_ipv4_mapped_loopback_is_rejected_for_public_names(settings) -> None:
    with pytest.raises(SafetyError, match="loopback"):
        validate_resolved_addresses(["::ffff:127.0.0.1"], settings, "example.com")


def test_resolved_ipv4_mapped_public_ip_is_allowed(settings) -> None:
    validate_resolved_addresses(["::ffff:93.184.216.34"], settings, "example.com")


def test_lab_range_opt_in(settings) -> None:
    settings.allow_lab_ranges = True
    validate_resolved_addresses(["192.168.1.5"], settings)


def test_rate_limiter_zero_interval() -> None:
    limiter = RateLimiter(0)
    limiter.wait_turn()
    limiter.wait_turn()


def test_safe_resolution_checks_addresses(monkeypatch, settings) -> None:
    import socket

    from network_diagnostics_monitor.safety import resolve_host_safely

    record = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [record, record])
    assert resolve_host_safely("example.com", settings, 0.1) == ["93.184.216.34"]


def test_safe_resolution_rejects_private_answer(monkeypatch, settings) -> None:
    import socket

    from network_diagnostics_monitor.safety import resolve_host_safely

    record = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", 0))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [record])
    with pytest.raises(SafetyError, match="blocked"):
        resolve_host_safely("example.com", settings, 0.1)


def test_safe_resolution_wraps_os_error(monkeypatch, settings) -> None:
    import socket

    from network_diagnostics_monitor.safety import resolve_host_safely

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("failed")))
    with pytest.raises(SafetyError, match="Could not safely resolve"):
        resolve_host_safely("example.com", settings, 0.1)


def test_public_hostname_cannot_resolve_to_loopback(settings) -> None:
    with pytest.raises(SafetyError, match="loopback"):
        validate_resolved_addresses(["127.0.0.1"], settings, "example.com")


def test_explicit_localhost_can_resolve_to_loopback(settings) -> None:
    validate_resolved_addresses(["127.0.0.1", "::1"], settings, "localhost")


def test_safe_resolution_enforces_timeout(monkeypatch, settings) -> None:
    import time

    from network_diagnostics_monitor.safety import resolve_host_safely

    def slow_lookup(*args, **kwargs):
        time.sleep(0.05)
        return []

    monkeypatch.setattr("socket.getaddrinfo", slow_lookup)
    with pytest.raises(SafetyError, match="Timed out resolving"):
        resolve_host_safely("example.com", settings, 0.001)
