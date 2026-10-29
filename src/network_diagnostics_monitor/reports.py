"""Incident and monitoring report generation in JSON, Markdown, and CSV formats."""

from __future__ import annotations

import csv
import io
import json
from html import escape
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .incidents import incident_duration_seconds
from .models import Device, Incident, Metric
from .recommendations import recommendations_as_dicts


def build_report(session: Session, *, generated_at: datetime | None = None) -> dict[str, Any]:
    """Build a deterministic-shape report from persisted devices, metrics, and incidents."""
    devices = session.scalars(select(Device).order_by(Device.name)).all()
    incidents = (
        session.scalars(
            select(Incident)
            .options(joinedload(Incident.device))
            .order_by(Incident.started_at.desc(), Incident.id.desc())
        )
        .unique()
        .all()
    )
    metric_count = session.scalar(select(func.count(Metric.id))) or 0
    oldest_metric = session.scalar(select(func.min(Metric.recorded_at)))
    newest_metric = session.scalar(select(func.max(Metric.recorded_at)))
    status_counts = Counter(item.status for item in incidents)
    severity_counts = Counter(item.severity for item in incidents)

    incident_rows: list[dict[str, Any]] = []
    for incident in incidents:
        incident_rows.append(
            {
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
            }
        )

    return {
        "report_version": 1,
        "generated_at": _iso(generated_at or datetime.now(UTC)),
        "data_mode": "persisted data; individual metric sources are retained in the database",
        "summary": {
            "device_count": len(devices),
            "simulated_device_count": sum(device.is_simulated for device in devices),
            "metric_count": metric_count,
            "incident_count": len(incidents),
            "active_incident_count": sum(
                item.status in {"open", "acknowledged"} for item in incidents
            ),
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
                "metric_count": session.scalar(
                    select(func.count(Metric.id)).where(Metric.device_id == device.id)
                )
                or 0,
                "incident_count": sum(
                    item["device"] == device.name for item in incident_rows
                ),
                "active_incident_count": sum(
                    item["device"] == device.name and item["status"] in {"open", "acknowledged"}
                    for item in incident_rows
                ),
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
        lines.append(
            "No incident-specific recommendations are available because no incidents are recorded."
        )
    for incident in report["incidents"]:
        lines.extend([f"### #{incident['id']} — {incident['title']}", ""])
        for index, item in enumerate(incident["recommendations"], start=1):
            lines.extend(
                [
                    f"{index}. **{item['action']}** ({item['priority']})",
                    f"   - Why: {item['rationale']}",
                    f"   - Verify: {item['verification']}",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation notes",
            "",
            "Recommendations are advisory and do not execute network changes. Confirm symptoms and follow local change-control procedures.",
            "Synthetic measurements should not be interpreted as evidence of a real production outage.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    """Render a self-contained responsive HTML report with escaped values."""
    summary = report["summary"]
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(incident['id']))}</td>"
        f"<td>{escape(str(incident['device']))}</td>"
        f"<td>{escape(str(incident['title']))}</td>"
        f"<td>{escape(str(incident['severity']))}</td>"
        f"<td>{escape(str(incident['status']))}</td>"
        f"<td>{escape(str(round(float(incident['duration_seconds']), 2)))}</td>"
        "</tr>"
        for incident in report["incidents"]
    ) or '<tr><td colspan="6">No incidents recorded</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Network Diagnostics Monitor Report</title>
<style>
:root{{color-scheme:light dark;--bg:#f5f7fa;--panel:#fff;--text:#172033;--muted:#5f6b7a;--line:#d8dee8}}@media(prefers-color-scheme:dark){{:root{{--bg:#12151b;--panel:#1b2029;--text:#edf1f7;--muted:#b3bdca;--line:#343b48}}}}
*{{box-sizing:border-box}}body{{margin:0;font-family:ui-sans-serif,system-ui,sans-serif;background:var(--bg);color:var(--text)}}main{{max-width:1100px;margin:0 auto;padding:24px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}}.card strong{{display:block;font-size:1.6rem}}.table-wrap{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid var(--line)}}th{{color:var(--muted)}}@media(max-width:600px){{main{{padding:12px}}}}
</style></head><body><main>
<h1>Network Diagnostics Monitor Report</h1><p>Generated: {escape(str(report['generated_at']))}</p>
<section class="cards"><article class="card"><strong>{escape(str(summary['device_count']))}</strong>Devices</article><article class="card"><strong>{escape(str(summary['metric_count']))}</strong>Metrics</article><article class="card"><strong>{escape(str(summary['incident_count']))}</strong>Incidents</article><article class="card"><strong>{escape(str(summary['active_incident_count']))}</strong>Active</article></section>
<h2>Incidents</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Device</th><th>Incident</th><th>Severity</th><th>Status</th><th>Duration (s)</th></tr></thead><tbody>{rows}</tbody></table></div>
</main></body></html>
"""


def render_incident_postmortem(report: dict[str, Any], incident_id: int) -> str:
    """Render a Markdown post-mortem for one persisted incident."""
    incident = next((item for item in report["incidents"] if item["id"] == incident_id), None)
    if incident is None:
        raise ValueError("incident was not found")
    recommendations = "; ".join(
        str(item["action"])
        for item in incident["recommendations"][:5]
    )
    timeline = "\n".join(
        _timeline_lines(incident)
    )
    resolution = recommendations or "Confirm the incident is resolved and document the remediation."
    return "\n".join(
        [
            f"# Post-mortem: {incident['title']}",
            "",
            "## Summary",
            "",
            f"- Incident: #{incident['id']} ({incident['severity']}, {incident['status']})",
            f"- Device: {incident['device']}",
            f"- Started: {incident['started_at'] or 'Unknown'}",
            f"- Resolved: {incident['resolved_at'] or 'Not resolved'}",
            f"- Duration: {incident['duration_seconds']:.2f} seconds",
            "",
            "## Timeline",
            "",
            timeline,
            "",
            "## Impact",
            "",
            f"The incident affected {_cell(str(incident['device']))} with {_cell(str(incident['description']))}.",
            "",
            "## Likely cause",
            "",
            _likely_cause(str(incident["kind"])),
            "",
            "## Resolution steps",
            "",
            resolution,
            "",
            "## Prevention",
            "",
            "Add or tune threshold-based monitoring, retain enough history for trend analysis, automate certificate renewal, and review alarms for repeat patterns.",
            "",
        ]
    )


def render_device_summary_csv(report: dict[str, Any]) -> str:
    """Render one guarded spreadsheet-safe summary row per device."""
    buffer = io.StringIO(newline="")
    fields = [
        "name",
        "type",
        "hostname",
        "location",
        "simulated",
        "metric_count",
        "incident_count",
        "active_incident_count",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for device in report["devices"]:
        writer.writerow({key: _spreadsheet_safe(device.get(key, "")) for key in fields})
    return buffer.getvalue()


def render_csv(report: dict[str, Any]) -> str:
    """Render one row per incident with recommendations flattened for spreadsheet use."""
    buffer = io.StringIO(newline="")
    fields = [
        "id",
        "device",
        "device_type",
        "kind",
        "title",
        "description",
        "severity",
        "status",
        "started_at",
        "acknowledged_at",
        "acknowledged_by",
        "resolved_at",
        "duration_seconds",
        "occurrence_count",
        "is_flapping",
        "recommendations",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for incident in report["incidents"]:
        row = {key: incident.get(key, "") for key in fields}
        row["recommendations"] = " | ".join(item["action"] for item in incident["recommendations"])
        writer.writerow({key: _spreadsheet_safe(value) for key, value in row.items()})
    return buffer.getvalue()


def _spreadsheet_safe(value: Any) -> Any:
    """Prefix spreadsheet formula-leading text while preserving numeric values."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _timeline_lines(incident: dict[str, Any]) -> str:
    lines = [f"- {incident['started_at']} — Incident opened"]
    if incident["acknowledged_at"]:
        lines.append(f"- {incident['acknowledged_at']} — Acknowledged by {incident['acknowledged_by'] or 'technician'}")
    if incident["resolved_at"]:
        lines.append(f"- {incident['resolved_at']} — Incident resolved")
    return "\n".join(lines)


def _likely_cause(kind: str) -> str:
    return {
        "high_latency": "Elevated latency suggests congestion, a slow gateway, or degradation on the network path.",
        "packet_loss": "Packet loss suggests link, gateway, interface, or upstream path quality problems.",
        "device_unavailable": "Availability loss suggests link, gateway, routing, firewall, or device reachability failure.",
        "dns_degradation": "DNS degradation suggests slow or unhealthy resolvers, resolver configuration, or DNS reachability problems.",
        "http_error": "An HTTP 5xx response suggests an application, dependency, reverse-proxy, or server-side failure.",
        "tls_expiry": "TLS findings suggest certificate validity, renewal automation, or certificate chain configuration issues.",
        "device_flapping": "Repeated state changes suggest unstable reachability, an interface, gateway, or upstream path.",
    }.get(kind, "The likely cause is inconclusive; correlate the incident description with application and network telemetry.")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _cell(value: str) -> str:
    """Escape table delimiters and newlines in Markdown cells."""
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")
