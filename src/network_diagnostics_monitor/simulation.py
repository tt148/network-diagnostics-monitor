"""Deterministic fictional device inventory and multi-day metric generation."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device, Metric

DEVICE_FIXTURES = (
    ("edge-router-01", "router", "router-01.simulated", "Network closet A", "Branch edge gateway"),
    ("core-switch-01", "switch", "switch-core.simulated", "Main rack", "Core switching"),
    ("access-point-01", "access_point", "ap-01.simulated", "Office floor 1", "Wireless access point"),
    ("access-point-02", "access_point", "ap-02.simulated", "Office floor 2", "Wireless access point"),
    ("dns-server-01", "dns_server", "dns-01.simulated", "Server room", "Internal name resolution"),
    ("web-server-01", "web_server", "web-01.simulated", "Server room", "Internal service endpoint"),
    ("nas-01", "nas", "nas-01.simulated", "Server room", "File storage"),
    ("printer-01", "printer", "printer-01.simulated", "Office floor 1", "Shared network printer"),
    ("vpn-gateway-01", "vpn_gateway", "vpn-01.simulated", "Main rack", "Remote access gateway"),
    ("access-switch-01", "switch", "switch-access.simulated", "Network closet B", "Access-layer switching"),
)


def seed_devices(session: Session) -> list[Device]:
    """Insert the ten fictional devices if they are not already present."""
    devices: list[Device] = []
    for name, kind, hostname, location, description in DEVICE_FIXTURES:
        device = session.scalar(select(Device).where(Device.name == name))
        if device is None:
            device = Device(
                name=name,
                device_type=kind,
                hostname=hostname,
                location=location,
                description=description,
                is_simulated=True,
            )
            session.add(device)
        devices.append(device)
    session.flush()
    return devices


def generate_metrics(
    session: Session,
    *,
    days: int = 3,
    interval_minutes: int = 60,
    seed: int = 42,
    end_time: datetime | None = None,
) -> int:
    """Generate reproducible metric history and built-in incident scenarios.

    Re-running with the same device/time window is idempotent: an existing metric
    with the same device, name and timestamp is not inserted twice.
    """
    if days < 1 or days > 30:
        raise ValueError("days must be between 1 and 30")
    if interval_minutes < 5 or interval_minutes > 1440:
        raise ValueError("interval_minutes must be between 5 and 1440")
    rng = random.Random(seed)
    devices = seed_devices(session)
    end = end_time or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    step = timedelta(minutes=interval_minutes)
    count = 0

    current = start
    while current <= end:
        hour_index = int((current - start).total_seconds() // step.total_seconds())
        for device in devices:
            latency = max(1.0, rng.gauss(22.0, 4.0))
            loss = max(0.0, min(100.0, rng.gauss(0.4, 0.35)))
            availability = 1.0
            dns_ms = max(4.0, rng.gauss(18.0, 3.0))
            http_status = 200

            # Scenarios are intentionally deterministic and easy to explain in docs.
            if device.name == "dns-server-01" and (18 <= hour_index % 120 <= 21 or current == end):
                dns_ms, availability = 1800.0, 0.0
            if device.name == "edge-router-01" and (30 <= hour_index % 120 <= 35 or current == end):
                latency, loss = 240.0, 18.0
            if device.name == "web-server-01" and (42 <= hour_index % 120 <= 46 or current == end):
                http_status, availability = 503, 0.0
            if device.name == "vpn-gateway-01" and (55 <= hour_index % 120 <= 62 or current == end):
                latency, loss = 155.0, 9.0
            if device.name == "access-point-02" and hour_index % 24 in {3, 4, 5, 6, 7, 8}:
                availability = 0.0 if hour_index % 24 in {4, 6, 8} else 1.0
            # Certificate remaining validity is a synthetic metric in days.
            cert_days = 9.0 if device.name == "web-server-01" else 180.0

            measurements = (
                ("latency_ms", latency, "ms", "critical" if latency >= 200 else "ok", "Round-trip estimate"),
                ("packet_loss_pct", loss, "%", "critical" if loss >= 10 else "ok", "Synthetic packet loss"),
                ("availability", availability, "ratio", "down" if availability < 1 else "up", "1=up, 0=down"),
                ("dns_resolution_ms", dns_ms, "ms", "critical" if dns_ms >= 1000 else "ok", "Synthetic DNS latency"),
                ("http_status", float(http_status), "code", "error" if http_status >= 500 else "ok", "Synthetic HTTP status"),
                ("tls_days_remaining", cert_days, "days", "warning" if cert_days <= 14 else "ok", "Synthetic certificate validity"),
            )
            for metric_name, value, unit, status, details in measurements:
                exists = session.scalar(
                    select(Metric.id).where(
                        Metric.device_id == device.id,
                        Metric.name == metric_name,
                        Metric.recorded_at == current,
                    )
                )
                if exists is not None:
                    continue
                session.add(
                    Metric(
                        device_id=device.id,
                        name=metric_name,
                        value=round(value, 3),
                        unit=unit,
                        status=status,
                        recorded_at=current,
                        source="simulation",
                        details=details,
                    )
                )
                count += 1
        current += step
    session.flush()
    return count
