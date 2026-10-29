"""Safety controls shared by all live check engines."""

from __future__ import annotations

import ipaddress
import queue
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import Settings


class SafetyError(ValueError):
    """Raised when a live probe violates the configured safety policy."""


@dataclass
class RateLimiter:
    """Process-local single-probe limiter with a configurable minimum interval."""

    minimum_interval: float = 2.0

    def __post_init__(self) -> None:
        self._last_started: float | None = None
        self._lock = threading.Lock()

    def wait_turn(self) -> None:
        """Wait until the minimum interval has elapsed, then reserve this turn."""
        with self._lock:
            now = time.monotonic()
            if self._last_started is not None:
                wait_for = self.minimum_interval - (now - self._last_started)
                if wait_for > 0:
                    time.sleep(wait_for)
            self._last_started = time.monotonic()


def hostname_from_target(target: str) -> str:
    """Extract a hostname from a bare hostname, IP, or HTTP(S) URL."""
    candidate = target.strip()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SafetyError("Only valid HTTP(S) URLs are supported.")
        return parsed.hostname.rstrip(".").lower()
    if not candidate or any(char in candidate for char in "/?#@"):
        raise SafetyError("Provide a hostname, IP address, or HTTP(S) URL.")
    return candidate.rstrip(".").lower()


def _unwrap_mapped(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Return the embedded IPv4 address of an IPv4-mapped IPv6 address (``::ffff:a.b.c.d``)."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for non-public ranges, including cloud metadata addresses."""
    address = _unwrap_mapped(address)
    if address.is_loopback:
        return False  # Allowed only through an explicit localhost allowlist entry.
    if (
        address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return True
    metadata_ranges = (
        ipaddress.ip_network("169.254.169.254/32"),
        ipaddress.ip_network("100.100.100.200/32"),
        ipaddress.ip_network("fd00:ec2::254/128"),
    )
    return any(address in network for network in metadata_ranges)


def validate_live_target(target: str, settings: Settings) -> str:
    """Validate a target against the explicit allowlist and IP-range policy.

    Hostnames are checked against the allowlist before resolution. Literal IPs are
    also checked against blocked ranges. DNS answers are checked again by live
    checkers before they connect, to reduce DNS-rebinding/SSRF risk.
    """
    hostname = hostname_from_target(target)
    allowlist = {item.lower().rstrip(".") for item in settings.allowed_targets}
    if hostname not in allowlist:
        raise SafetyError(f"Target {hostname!r} is not in NDM_ALLOWED_TARGETS.")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not settings.allow_lab_ranges and _is_blocked_ip(address):
        raise SafetyError(f"Target IP {address} is blocked by the live safety policy.")
    return hostname


def validate_resolved_addresses(
    addresses: list[str], settings: Settings, hostname: str | None = None
) -> None:
    """Reject private or special-use DNS answers unless lab ranges are enabled.

    Loopback is allowed only when the original target itself is an explicitly
    allowlisted loopback address or ``localhost``; public names cannot resolve
    to loopback to bypass the target policy.
    """
    if settings.allow_lab_ranges:
        return
    normalized_host = (hostname or "").lower().rstrip(".")
    explicit_loopback = normalized_host in {"localhost", "127.0.0.1", "::1"}
    for raw_address in addresses:
        try:
            address = _unwrap_mapped(ipaddress.ip_address(raw_address))
        except ValueError:
            continue
        if address.is_loopback:
            if explicit_loopback:
                continue
            raise SafetyError(
                f"Resolved address {address} is loopback but the target is not an explicit localhost target."
            )
        if _is_blocked_ip(address):
            raise SafetyError(f"Resolved address {address} is blocked by the live safety policy.")


def resolve_host_safely(hostname: str, settings: Settings, timeout: float) -> list[str]:
    """Resolve host addresses and apply blocked-range checks before connections."""
    result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def lookup() -> None:
        try:
            result_queue.put(
                (
                    True,
                    socket.getaddrinfo(
                        hostname,
                        None,
                        family=socket.AF_UNSPEC,
                        type=socket.SOCK_STREAM,
                    ),
                )
            )
        except OSError as exc:
            result_queue.put((False, exc))

    worker = threading.Thread(target=lookup, name="ndm-resolver", daemon=True)
    worker.start()
    try:
        succeeded, result = result_queue.get(timeout=timeout)
    except queue.Empty as exc:
        raise SafetyError(f"Timed out resolving target {hostname!r} after {timeout}s.") from exc
    if not succeeded:
        raise SafetyError(f"Could not safely resolve target {hostname!r}: {result}") from result
    records = result
    addresses = sorted({record[4][0] for record in records})
    validate_resolved_addresses(addresses, settings, hostname)
    return addresses
