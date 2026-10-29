"""Typer command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .checks.dns import check_dns
from .checks.http import check_http
from .checks.latency import check_latency
from .config import Settings, get_settings
from .database import create_schema, make_engine, make_session_factory
from .diagnosis import diagnose_target
from .incidents import acknowledge_incident, replay_incidents, resolve_incident
from .models import Incident
from .recommendations import recommendations_as_dicts
from .reports import (
    build_report,
    render_csv,
    render_device_summary_csv,
    render_html,
    render_incident_postmortem,
    render_json,
    render_markdown,
)
from .safety import RateLimiter, SafetyError
from .simulation import generate_metrics, seed_devices

app = typer.Typer(
    name="network-diagnostics",
    help="Safe, simulated-first network diagnostics.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Keep subcommands explicit, including the diagnose command."""


@app.command()
def diagnose(
    target: Annotated[str, typer.Argument(help="Hostname, IP, or HTTP(S) URL.")],
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="simulated (default) or live (allowlist required)."),
    ] = None,
) -> None:
    """Run DNS, latency, and HTTP/TLS checks for one target."""
    settings: Settings = get_settings()
    selected_mode = mode or settings.mode
    if selected_mode not in {"simulated", "live"}:
        raise typer.BadParameter("mode must be 'simulated' or 'live'")
    limiter = RateLimiter(settings.min_check_interval_seconds)
    try:
        dns_result = check_dns(target, mode=selected_mode, settings=settings, limiter=limiter)
        latency_result = check_latency(
            target, mode=selected_mode, settings=settings, limiter=limiter
        )
        http_result = check_http(target, mode=selected_mode, settings=settings, limiter=limiter)
        result = {
            "target": target,
            "mode": selected_mode,
            "dns": dns_result,
            "latency": latency_result,
            "http": http_result,
            "diagnosis": diagnose_target(target, dns_result, latency_result, http_result),
        }
    except (SafetyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command()
def seed(
    days: Annotated[int, typer.Option(help="Days of synthetic metric history to generate.")] = 3,
    interval_minutes: Annotated[int, typer.Option(help="Minutes between synthetic samples.")] = 60,
    seed_value: Annotated[int, typer.Option("--seed", help="Deterministic random seed.")] = 42,
) -> None:
    """Create fictional devices, generate deterministic metrics, and evaluate incidents."""
    engine = make_engine()
    create_schema(engine)
    factory = make_session_factory(engine)
    with factory.begin() as session:
        devices = seed_devices(session)
        metric_count = generate_metrics(
            session, days=days, interval_minutes=interval_minutes, seed=seed_value
        )
        incidents = replay_incidents(session)
        typer.echo(
            json.dumps(
                {
                    "devices": len(devices),
                    "metrics_inserted": metric_count,
                    "incidents_created_or_updated": len(incidents),
                    "mode": "simulated",
                },
                indent=2,
            )
        )


@app.command("incidents")
def list_incidents(
    status: Annotated[str | None, typer.Option(help="Optional status filter.")] = None,
) -> None:
    """List persisted incident history."""
    engine = make_engine()
    create_schema(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        query = session.query(Incident).order_by(Incident.started_at.desc())
        if status:
            if status not in {"open", "acknowledged", "resolved"}:
                raise typer.BadParameter("status must be open, acknowledged, or resolved")
            query = query.filter(Incident.status == status)
        typer.echo(
            json.dumps(
                [
                    {
                        "id": item.id,
                        "device": item.device.name,
                        "kind": item.kind,
                        "severity": item.severity,
                        "status": item.status,
                        "started_at": item.started_at.isoformat(),
                        "duration_seconds": item.duration_seconds,
                        "is_flapping": item.is_flapping,
                    }
                    for item in query.all()
                ],
                indent=2,
            )
        )


@app.command("acknowledge")
def acknowledge(
    incident_id: Annotated[int, typer.Argument(help="Incident ID to acknowledge.")],
    by: Annotated[str, typer.Option("--by", help="Technician name.")] = "technician",
) -> None:
    """Acknowledge an open incident."""
    engine = make_engine()
    create_schema(engine)
    with make_session_factory(engine).begin() as session:
        incident = acknowledge_incident(session, incident_id, by)
        typer.echo(json.dumps({"id": incident.id, "status": incident.status}))


@app.command("resolve")
def resolve(incident_id: Annotated[int, typer.Argument(help="Incident ID to resolve.")]) -> None:
    """Resolve an incident and calculate its duration."""
    engine = make_engine()
    create_schema(engine)
    with make_session_factory(engine).begin() as session:
        incident = resolve_incident(session, incident_id)
        typer.echo(
            json.dumps(
                {
                    "id": incident.id,
                    "status": incident.status,
                    "duration_seconds": incident.duration_seconds,
                }
            )
        )


@app.command()
def recommendations(
    incident_id: Annotated[
        int | None, typer.Argument(help="Optional incident ID; omit to list all incidents.")
    ] = None,
) -> None:
    """Show advisory troubleshooting steps for one or all persisted incidents."""
    engine = make_engine()
    create_schema(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        if incident_id is not None:
            incident = session.get(Incident, incident_id)
            if incident is None:
                raise typer.BadParameter(f"incident {incident_id} was not found")
            results = [
                {
                    "incident_id": incident.id,
                    "title": incident.title,
                    "severity": incident.severity,
                    "recommendations": recommendations_as_dicts(incident),
                }
            ]
        else:
            results = [
                {
                    "incident_id": incident.id,
                    "title": incident.title,
                    "severity": incident.severity,
                    "recommendations": recommendations_as_dicts(incident),
                }
                for incident in session.query(Incident).order_by(Incident.started_at.desc()).all()
            ]
        typer.echo(json.dumps(results, indent=2, sort_keys=True))


@app.command()
def report(
    format: Annotated[
        str, typer.Option("--format", help="Report format: json, markdown, or csv.")
    ] = "markdown",
    output: Annotated[
        str | None, typer.Option("--output", help="Optional output file path.")
    ] = None,
    incident_id: Annotated[
        int | None, typer.Option("--incident-id", help="Incident ID for a post-mortem report.")
    ] = None,
) -> None:
    """Generate monitoring, HTML, post-mortem, or per-device reports."""
    if format not in {"json", "markdown", "csv", "html", "postmortem", "device-csv"}:
        raise typer.BadParameter(
            "format must be json, markdown, csv, html, postmortem, or device-csv"
        )
    engine = make_engine()
    create_schema(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        report_data = build_report(session)
    if format == "postmortem":
        if incident_id is None:
            raise typer.BadParameter("--incident-id is required for postmortem format")
        rendered = render_incident_postmortem(report_data, incident_id)
    else:
        renderers = {
            "json": render_json,
            "markdown": render_markdown,
            "csv": render_csv,
            "html": render_html,
            "device-csv": render_device_summary_csv,
        }
        rendered = renderers[format](report_data)
    if output:
        destination = Path(output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8", newline="")
        typer.echo(
            json.dumps(
                {
                    "format": format,
                    "output": str(destination),
                    "bytes": len(rendered.encode("utf-8")),
                }
            )
        )
    else:
        typer.echo(rendered, nl=False)


if __name__ == "__main__":
    app()
