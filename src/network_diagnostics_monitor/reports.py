"""Incident and monitoring report generation in JSON, Markdown, and CSV formats."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .incidents import incident_duration_seconds
from .models import Device, Incident, Metric
from .recommendations import recommendations_as_dicts


def build_report(session: Session, *, generated_at: datetime | None = None) -> dict[str, Any]:
    """Build a deterministic-shape report from persisted devices, metrics, and incidents."""
    devices = session.scalars(select(Device).order_by(Device.name)).all()
    incidents = session.scalars(
        select(Incident).options(joinedload(Incident.device)).order_by(Incident.started_at.desc(), Incident.id.desc())
    ).unique().all()
    metric_count = session.scalar(select(func.count(Metric.id))) or 0
    oldest_metric = session.scalar(select(func.min(Metric.recorded_at)))
    newest_metric = session.scalar(select(func.max(Metric.recorded_at)))
    status_counts = Counter(item.status for item in incidents)
    severity_counts = Counter(item.severity for item in incidents)

    incident_rows: list[dict[str, Any]] = []
    for incident in incidents:
        incident_rows.append({
            "id": incident.id,
            "device": incident.device.name,
            "device_type": incident.device.device_type,
            "kind": incident.kind,
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "status": incident.status,
            "started_at": _iso(incident.started_at),
            "acknowledged_at": _iso(incident.acknowledged_at),
            "acknowledged_by": incident.acknowledged_by,
            "resolved_at": _iso(incident.resolved_at),
            "duration_seconds": round(incident_duration_seconds(incident, now=generated_at), 2),
            "occurrence_count": incident.occurrence_count,
            "is_flapping": incident.is_flapping,
            "recommendations": recommendations_as_dicts(incident),
        })

    return {
        "report_version": 1,
        "generated_at": _iso(generated_at or datetime.now(timezone.utc)),
        "data_mode": "persisted data; individual metric sources are retained in the database",
        "summary": {
            "device_count": len(devices),
            "simulated_device_count": sum(device.is_simulated for device in devices),
            "metric_count": metric_count,
            "incident_count": len(incidents),
            "active_incident_count": sum(item.status in {"open", "acknowledged"} for item in incidents),
            "status_counts": dict(sorted(status_counts.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
            "oldest_metric_at": _iso(oldest_metric),
            "newest_metric_at": _iso(newest_metric),
        },
        "devices": [
            {
                "name": device.name,
                "type": device.device_type,
                "hostname": device.hostname,
                "location": device.location,
                "simulated": device.is_simulated,
            }
            for device in devices
        ],
        "incidents": incident_rows,
    }


def render_json(report: dict[str, Any]) -> str:
    """Render a report as indented JSON."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable summary and incident table as Markdown."""
    summary = report["summary"]
    lines = [
        "# Network Diagnostics Monitor Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Devices: {summary['device_count']} ({summary['simulated_device_count']} simulated)",
        f"- Metrics: {summary['metric_count']}",
        f"- Incidents: {summary['incident_count']} ({summary['active_incident_count']} active)",
        f"- Metric window: {summary['oldest_metric_at'] or 'No metrics'} to {summary['newest_metric_at'] or 'No metrics'}",
        "",
        "## Incident summary",
        "",
        "| ID | Device | Incident | Severity | Status | Duration (s) |",
        "|---:|---|---|---|---|---:|",
    ]
    for incident in report["incidents"]:
        lines.append(
            f"| {incident['id']} | {_cell(incident['device'])} | {_cell(incident['title'])} "
            f"| {incident['severity']} | {incident['status']} | {incident['duration_seconds']:.2f} |"
        )
    if not report["incidents"]:
        lines.append("| — | — | No incidents recorded | — | — | — |")

    lines.extend(["", "## Troubleshooting recommendations", ""])
    if not report["incidents"]:
        lines.append("No incident-specific recommendations are available because no incidents are recorded.")
    for incident in report["incidents"]:
        lines.extend([f"### #{incident['id']} — {incident['title']}", ""])
        for index, item in enumerate(incident["recommendations"], start=1):
            lines.extend([
                f"{index}. **{item['action']}** ({item['priority']})",
                f"   - Why: {item['rationale']}",
                f"   - Verify: {item['verification']}",
            ])
        lines.append("")
    lines.extend([
        "## Interpretation notes",
        "",
        "Recommendations are advisory and do not execute network changes. Confirm symptoms and follow local change-control procedures.",
        "Synthetic measurements should not be interpreted as evidence of a real production outage.",
        "",
    ])
    return "\n".join(lines)


def render_csv(report: dict[str, Any]) -> str:
    """Render one row per incident with recommendations flattened for spreadsheet use."""
    buffer = io.StringIO(newline="")
    fields = [
        "id", "device", "device_type", "kind", "title", "description", "severity", "status",
        "started_at", "acknowledged_at", "acknowledged_by", "resolved_at", "duration_seconds",
        "occurrence_count", "is_flapping", "recommendations",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for incident in report["incidents"]:
        row = {key: incident.get(key, "") for key in fields}
        row["recommendations"] = " | ".join(item["action"] for item in incident["recommendations"])
        writer.writerow(row)
    return buffer.getvalue()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _cell(value: str) -> str:
    """Escape table delimiters and newlines in Markdown cells."""
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
