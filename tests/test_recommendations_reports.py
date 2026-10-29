"""Tests for troubleshooting recommendations and report exports."""

import csv
import json
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from network_diagnostics_monitor.cli import app
from network_diagnostics_monitor.database import create_schema, make_engine, make_session_factory
from network_diagnostics_monitor.models import Device, Incident, Metric
from network_diagnostics_monitor.recommendations import (
    recommendations_as_dicts,
    recommendations_for,
)
from network_diagnostics_monitor.reports import (
    build_report,
    render_csv,
    render_device_summary_csv,
    render_html,
    render_incident_postmortem,
    render_json,
    render_markdown,
)
from network_diagnostics_monitor.simulation import seed_devices


def _session():
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    factory = make_session_factory(engine)
    return engine, factory()


def _incident(session, kind="high_latency", *, status="open"):
    device = session.query(Device).first()
    if device is None:
        device = seed_devices(session)[0]
    start = datetime(2026, 10, 20, tzinfo=UTC)
    incident = Incident(
        device_id=device.id,
        kind=kind,
        title=f"{device.name}: {kind}",
        description="Synthetic test incident",
        severity="major",
        status=status,
        started_at=start,
        last_observed_at=start + timedelta(minutes=5),
    )
    session.add(incident)
    session.flush()
    return incident


def test_recommendations_are_actionable_and_do_not_mutate_incident():
    engine, session = _session()
    try:
        incident = _incident(session, "dns_degradation")
        before = (incident.status, incident.description)
        items = recommendations_for(incident)
        assert len(items) >= 3
        assert all(item.action and item.rationale and item.verification for item in items)
        assert (incident.status, incident.description) == before
        assert recommendations_as_dicts(incident)[0]["priority"]
    finally:
        session.close()
        engine.dispose()


def test_unknown_incident_kind_gets_safe_generic_guidance():
    engine, session = _session()
    try:
        incident = _incident(session, "unmapped_custom_alert")
        items = recommendations_for(incident)
        assert len(items) == 3
        assert any("Escalate" in item.action for item in items)
    finally:
        session.close()
        engine.dispose()


def test_report_summary_and_incident_recommendations():
    engine, session = _session()
    try:
        seed_devices(session)
        _incident(session, "tls_expiry")
        session.add(
            Metric(
                device_id=session.query(Device).first().id,
                name="latency_ms",
                value=35.0,
                unit="ms",
                status="ok",
                recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
                source="simulation",
            )
        )
        session.flush()
        report = build_report(session, generated_at=datetime(2026, 10, 21, tzinfo=UTC))
        assert report["summary"]["device_count"] == 10
        assert report["summary"]["simulated_device_count"] == 10
        assert report["summary"]["metric_count"] == 1
        assert report["summary"]["incident_count"] == 1
        assert report["incidents"][0]["recommendations"]
        assert report["incidents"][0]["device"]
    finally:
        session.close()
        engine.dispose()


def test_report_renderers_produce_valid_json_markdown_and_csv():
    engine, session = _session()
    try:
        _incident(session, "http_error")
        report = build_report(session, generated_at=datetime(2026, 10, 21, tzinfo=UTC))
        decoded = json.loads(render_json(report))
        assert decoded["summary"]["incident_count"] == 1
        markdown = render_markdown(report)
        assert "Troubleshooting recommendations" in markdown
        assert "http_error" in markdown
        rows = list(csv.DictReader(render_csv(report).splitlines()))
        assert len(rows) == 1
        assert "Review application logs" in rows[0]["recommendations"]
    finally:
        session.close()
        engine.dispose()


def test_html_report_is_self_contained_and_escapes_values():
    engine, session = _session()
    try:
        incident = _incident(session, "http_error")
        incident.title = "<script>alert('x')</script>"
        session.flush()
        report = build_report(session, generated_at=datetime(2026, 10, 21, tzinfo=UTC))
        rendered = render_html(report)
        assert "<!doctype html>" in rendered
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered
        assert "@media(prefers-color-scheme:dark)" in rendered
    finally:
        session.close()
        engine.dispose()


def test_postmortem_and_device_csv_include_required_sections():
    engine, session = _session()
    try:
        seed_devices(session)
        incident = _incident(session, "dns_degradation")
        session.flush()
        report = build_report(session, generated_at=datetime(2026, 10, 21, tzinfo=UTC))
        postmortem = render_incident_postmortem(report, incident.id)
        assert "## Summary" in postmortem
        assert "## Timeline" in postmortem
        assert "## Impact" in postmortem
        assert "## Likely cause" in postmortem
        assert "## Resolution steps" in postmortem
        assert "## Prevention" in postmortem
        assert "DNS" in postmortem

        device_csv = render_device_summary_csv(report)
        rows = list(csv.DictReader(device_csv.splitlines()))
        assert len(rows) == 10
        assert {"name", "metric_count", "incident_count", "active_incident_count"} <= set(rows[0])
    finally:
        session.close()
        engine.dispose()


def test_csv_guards_spreadsheet_formula_injection():
    report = {
        "incidents": [
            {
                "id": 1,
                "device": '=HYPERLINK("x")',
                "device_type": "router",
                "kind": "test",
                "title": "+CMD('bad')",
                "description": "@SUM(1,1)",
                "severity": "warning",
                "status": "open",
                "started_at": None,
                "acknowledged_at": None,
                "acknowledged_by": None,
                "resolved_at": None,
                "duration_seconds": 1,
                "occurrence_count": 1,
                "is_flapping": False,
                "recommendations": [],
            }
        ]
    }
    rendered = render_csv(report)
    assert "'=HYPERLINK" in rendered
    assert "'+CMD" in rendered
    assert "'@SUM" in rendered


def test_empty_report_rendering_is_valid():
    engine, session = _session()
    try:
        report = build_report(session, generated_at=datetime(2026, 10, 21, tzinfo=UTC))
        assert report["summary"]["device_count"] == 0
        assert "No incidents recorded" in render_markdown(report)
        assert json.loads(render_json(report))["incidents"] == []
        assert len(list(csv.DictReader(render_csv(report).splitlines()))) == 0
    finally:
        session.close()
        engine.dispose()


def test_cli_report_writes_requested_file(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("NDM_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    output = tmp_path / "reports" / "summary.json"
    result = runner.invoke(app, ["report", "--format", "json", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["device_count"] == 0


def test_cli_html_report_writes_requested_file(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("NDM_DATABASE_URL", f"sqlite:///{db_path}")
    output = tmp_path / "report.html"
    result = CliRunner().invoke(app, ["report", "--format", "html", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "<!doctype html>" in output.read_text(encoding="utf-8")


def test_cli_postmortem_requires_incident_id(tmp_path, monkeypatch, normalize_cli_output):
    monkeypatch.setenv("NDM_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    result = CliRunner().invoke(app, ["report", "--format", "postmortem"])
    output = normalize_cli_output(result.output)
    assert result.exit_code != 0
    assert "--incident-id is required" in output


def test_cli_rejects_unknown_report_format(normalize_cli_output):
    result = CliRunner().invoke(app, ["report", "--format", "xml"])
    output = normalize_cli_output(result.output)
    assert result.exit_code != 0
    assert "Invalid value:" in output
    assert "device-csv" in output


def test_cli_recommendations_for_missing_incident_is_friendly(
    tmp_path, monkeypatch, normalize_cli_output
):
    monkeypatch.setenv("NDM_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    result = CliRunner().invoke(app, ["recommendations", "999"])
    output = normalize_cli_output(result.output)
    assert result.exit_code != 0
    assert "incident 999 was not found" in output
