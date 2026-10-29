"""Threshold-based incident detection and lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Device, Incident, Metric

ACTIVE_STATUSES = ("open", "acknowledged")
DEFAULT_THRESHOLDS = {
    "latency_ms": 150.0,
    "packet_loss_pct": 5.0,
    "dns_resolution_ms": 500.0,
    "http_status": 500.0,
    "tls_days_remaining": 14.0,
}
SEVERITY_THRESHOLDS = {
    "latency_ms": (300.0, 150.0),
    "packet_loss_pct": (20.0, 10.0),
    "dns_resolution_ms": (1500.0, 750.0),
    "http_status": (500.0, 500.0),
    "tls_days_remaining": (3.0, 7.0),
}


def _utc(value: datetime | None = None) -> datetime:
    return value or datetime.now(UTC)


def _elapsed_seconds(start: datetime, end: datetime) -> float:
    """Subtract datetimes consistently when SQLite returns naive UTC values."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(0.0, (end - start).total_seconds())


def _abnormal(metric: Metric, thresholds: dict[str, float]) -> bool:
    if metric.name == "availability":
        return metric.value < 1.0
    if metric.name == "http_status":
        return metric.value >= thresholds.get(metric.name, 500.0)
    if metric.name == "tls_days_remaining":
        return metric.value <= thresholds.get(metric.name, 14.0)
    return metric.value >= thresholds.get(metric.name, float("inf"))


def _severity(metric: Metric) -> str:
    high, medium = SEVERITY_THRESHOLDS.get(metric.name, (1.0, 1.0))
    if metric.name == "tls_days_remaining":
        return "critical" if metric.value <= high else "warning"
    if metric.name == "http_status":
        return "critical"
    if metric.value >= high:
        return "critical"
    if metric.value >= medium:
        return "major"
    return "warning"


def _incident_kind(metric_name: str) -> str:
    return {
        "latency_ms": "high_latency",
        "packet_loss_pct": "packet_loss",
        "availability": "device_unavailable",
        "dns_resolution_ms": "dns_degradation",
        "http_status": "http_error",
        "tls_days_remaining": "tls_expiry",
    }.get(metric_name, metric_name)


def evaluate_incidents(
    session: Session,
    *,
    thresholds: dict[str, float] | None = None,
    now: datetime | None = None,
    flapping_window: int = 12,
    flapping_transitions: int = 4,
) -> list[Incident]:
    """Evaluate each device's latest measurements, opening or resolving incidents.

    Existing open/acknowledged incidents are updated instead of duplicated.
    Healthy latest readings resolve the corresponding active incident.
    """
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    current_time = _utc(now)
    latest_rows = session.execute(
        select(Metric, Device)
        .join(Device, Metric.device_id == Device.id)
        .order_by(Metric.recorded_at.desc(), Metric.id.desc())
    ).all()

    latest: dict[tuple[int, str], tuple[Metric, Device]] = {}
    for metric, device in latest_rows:
        latest.setdefault((metric.device_id, metric.name), (metric, device))

    changed: list[Incident] = []
    for (device_id, metric_name), (metric, device) in latest.items():
        kind = _incident_kind(metric_name)
        active = session.scalar(
            select(Incident)
            .where(
                Incident.device_id == device_id,
                Incident.kind == kind,
                Incident.status.in_(ACTIVE_STATUSES),
            )
            .order_by(Incident.started_at.desc())
        )
        abnormal = _abnormal(metric, limits)
        if abnormal:
            if active:
                active.last_observed_at = metric.recorded_at
                active.occurrence_count += 1
                active.severity = _severity(metric)
                active.description = f"{metric_name} measured {metric.value:g} {metric.unit}".strip()
                changed.append(active)
            else:
                incident = Incident(
                    device_id=device_id,
                    kind=kind,
                    title=f"{device.name}: {_title(kind)}",
                    description=f"{metric_name} measured {metric.value:g} {metric.unit}".strip(),
                    severity=_severity(metric),
                    status="open",
                    started_at=metric.recorded_at,
                    last_observed_at=metric.recorded_at,
                )
                session.add(incident)
                changed.append(incident)
        elif active:
            active.status = "resolved"
            active.resolved_at = metric.recorded_at
            active.duration_seconds = _elapsed_seconds(active.started_at, metric.recorded_at)
            changed.append(active)

    # Flapping is based on recent up/down transitions; the input is synthetic metrics only.
    devices = session.scalars(select(Device)).all()
    for device in devices:
        history = list(
            session.scalars(
                select(Metric)
                .where(Metric.device_id == device.id, Metric.name == "availability")
                .order_by(Metric.recorded_at.desc(), Metric.id.desc())
                .limit(flapping_window)
            )
        )
        if len(history) < 2:
            continue
        states = [metric.value >= 1.0 for metric in reversed(history)]
        transitions = sum(left != right for left, right in pairwise(states))
        kind = "device_flapping"
        active = session.scalar(
            select(Incident).where(
                Incident.device_id == device.id,
                Incident.kind == kind,
                Incident.status.in_(ACTIVE_STATUSES),
            )
        )
        if transitions >= flapping_transitions:
            if active:
                active.is_flapping = True
                active.last_observed_at = history[0].recorded_at
                active.occurrence_count += 1
                changed.append(active)
            else:
                incident = Incident(
                    device_id=device.id,
                    kind=kind,
                    title=f"{device.name}: availability flapping",
                    description=f"{transitions} up/down transitions in {len(history)} recent samples",
                    severity="major",
                    status="open",
                    started_at=history[-1].recorded_at,
                    last_observed_at=history[0].recorded_at,
                    is_flapping=True,
                )
                session.add(incident)
                changed.append(incident)
        elif active:
            active.status = "resolved"
            active.resolved_at = current_time
            active.duration_seconds = _elapsed_seconds(active.started_at, current_time)
            changed.append(active)

    session.flush()
    return changed


def acknowledge_incident(
    session: Session, incident_id: int, acknowledged_by: str, *, now: datetime | None = None
) -> Incident:
    """Acknowledge an open incident; reject missing or already-resolved incidents."""
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise ValueError(f"Incident {incident_id} was not found")
    if incident.status == "resolved":
        raise ValueError("A resolved incident cannot be acknowledged")
    if not acknowledged_by.strip():
        raise ValueError("acknowledged_by must not be blank")
    incident.status = "acknowledged"
    incident.acknowledged_by = acknowledged_by.strip()
    incident.acknowledged_at = _utc(now)
    session.flush()
    return incident


def resolve_incident(
    session: Session, incident_id: int, *, now: datetime | None = None
) -> Incident:
    """Resolve an incident and calculate its duration."""
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise ValueError(f"Incident {incident_id} was not found")
    if incident.status == "resolved":
        return incident
    resolved_at = _utc(now)
    incident.status = "resolved"
    incident.resolved_at = resolved_at
    incident.duration_seconds = _elapsed_seconds(incident.started_at, resolved_at)
    session.flush()
    return incident


def incident_duration_seconds(incident: Incident, *, now: datetime | None = None) -> float:
    """Return the persisted duration or the live duration of an active incident."""
    end = incident.resolved_at or _utc(now)
    return (
        max(0.0, incident.duration_seconds)
        if incident.duration_seconds is not None
        else _elapsed_seconds(incident.started_at, end)
    )


def _title(kind: str) -> str:
    return {
        "high_latency": "high latency",
        "packet_loss": "packet loss",
        "device_unavailable": "device unavailable",
        "dns_degradation": "DNS degradation",
        "http_error": "HTTP server error",
        "tls_expiry": "TLS certificate nearing expiry",
    }.get(kind, kind.replace("_", " "))
