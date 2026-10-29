"""DNS diagnostics with deterministic simulated and guarded live modes."""

from __future__ import annotations

import time
from typing import Any

import dns.exception
import dns.resolver

from ..config import Settings
from ..safety import RateLimiter, validate_live_target

DNS_RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT")


def check_dns(
    target: str,
    *,
    mode: str = "simulated",
    settings: Settings | None = None,
    record_types: tuple[str, ...] = DNS_RECORD_TYPES,
    limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Check common DNS record types and optionally compare two resolvers."""
    settings = settings or Settings()
    if mode == "simulated":
        return {
            "target": target,
            "mode": "simulated",
            "status": "ok",
            "duration_ms": 12.4,
            "records": {
                "A": ["192.0.2.10"],
                "AAAA": ["2001:db8::10"],
                "CNAME": [],
                "MX": ["10 mail.example.com."],
                "NS": ["ns1.example.com."],
                "TXT": ['"simulated-diagnostic-record"'],
            },
            "resolver_comparison": {"simulated-resolver-a": "match", "simulated-resolver-b": "match"},
            "message": "SIMULATED: no DNS request was sent.",
        }
    if mode != "live":
        raise ValueError("mode must be 'simulated' or 'live'")

    hostname = validate_live_target(target, settings)
    (limiter or RateLimiter(settings.min_check_interval_seconds)).wait_turn()
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = settings.timeout_seconds
    resolver.lifetime = settings.timeout_seconds
    records: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    started = time.perf_counter()
    for record_type in record_types:
        if record_type not in DNS_RECORD_TYPES:
            raise ValueError(f"Unsupported DNS record type: {record_type}")
        try:
            answer = resolver.resolve(hostname, record_type, lifetime=settings.timeout_seconds)
            records[record_type] = [record.to_text() for record in answer]
        except dns.resolver.NXDOMAIN:
            errors[record_type] = "NXDOMAIN"
        except dns.resolver.NoNameservers:
            errors[record_type] = "SERVFAIL"
        except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
            errors[record_type] = "TIMEOUT"
        except dns.resolver.NoAnswer:
            records[record_type] = []
        except dns.exception.DNSException as exc:
            errors[record_type] = type(exc).__name__.upper()
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    comparison: dict[str, str] = {}
    if len(settings.dns_resolvers) >= 2:
        baseline = set(records.get("A", []))
        for resolver_ip in settings.dns_resolvers[:2]:
            custom = dns.resolver.Resolver(configure=False)
            custom.nameservers = [resolver_ip]
            custom.timeout = settings.timeout_seconds
            custom.lifetime = settings.timeout_seconds
            try:
                comparison[resolver_ip] = (
                    "match" if set(str(r) for r in custom.resolve(hostname, "A")) == baseline else "different"
                )
            except dns.exception.DNSException as exc:
                comparison[resolver_ip] = type(exc).__name__.upper()

    status = "error" if errors else ("slow" if duration_ms > settings.slow_dns_threshold_ms else "ok")
    return {
        "target": hostname,
        "mode": "live",
        "status": status,
        "duration_ms": duration_ms,
        "records": records,
        "errors": errors,
        "resolver_comparison": comparison,
        "message": "Live DNS result; only an allowlisted hostname was queried.",
    }
