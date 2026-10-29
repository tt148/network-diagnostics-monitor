"""API and dashboard tests using a temporary SQLite database."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from network_diagnostics_monitor.api import create_app
from network_diagnostics_monitor.database import make_session_factory
from network_diagnostics_monitor.models import Device, Incident
from network_diagnostics_monitor.simulation import generate_metrics, seed_devices


def _client(tmp_path):
    database = tmp_path / "api-test.db"
    app = create_app(f"sqlite:///{database}")
    client = TestClient(app)
    factory = make_session_factory(app.state.engine)
    with factory.begin() as session:
        seed_devices(session)
        generate_metrics(session, days=1, interval_minutes=360, seed=13)
        device = session.query(Device).order_by(Device.id).first()
        incident = Incident(
            device_id=device.id,
            kind="high_latency",
            title=f"{device.name}: high latency",
            description="Synthetic test incident",
            severity="major",
            status="open",
            started_at=datetime(2026, 10, 28, tzinfo=UTC),
            last_observed_at=datetime(2026, 10, 28, 0, 5, tzinfo=UTC),
        )
        session.add(incident)
        session.add(
            Incident(
                device_id=device.id,
                kind="http_error",
                title=f"{device.name}: HTTP 503 burst",
                description="Synthetic resolved HTTP 503 incident",
                severity="critical",
                status="resolved",
                started_at=datetime(2026, 10, 27, 6, tzinfo=UTC),
                resolved_at=datetime(2026, 10, 27, 11, tzinfo=UTC),
                duration_seconds=18000,
                last_observed_at=datetime(2026, 10, 27, 11, tzinfo=UTC),
            )
        )
    return app, client


def test_health_and_summary_endpoints(tmp_path):
    app, client = _client(tmp_path)
    try:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        summary = client.get("/api/summary").json()
        assert summary["device_count"] == 10
        assert summary["simulated_device_count"] == 10
        assert summary["metric_count"] > 0
        assert summary["active_incident_count"] == 1
        assert summary["resolved_incident_count"] == 1
        assert summary["status_counts"] == {"open": 1, "resolved": 1}
    finally:
        app.state.engine.dispose()


def test_devices_metrics_and_bounds(tmp_path):
    app, client = _client(tmp_path)
    try:
        devices = client.get("/api/devices").json()
        assert len(devices) == 10
        assert devices[0]["is_simulated"] is True
        device_id = devices[0]["id"]
        assert client.get(f"/api/devices/{device_id}").status_code == 200
        assert client.get(f"/api/devices/{device_id}/metrics?limit=3").status_code == 200
        assert len(client.get("/api/metrics?limit=2").json()) == 2
        assert client.get("/api/metrics?limit=9999").status_code == 422
        assert client.get("/api/devices/9999").status_code == 404
    finally:
        app.state.engine.dispose()


def test_incident_filter_recommendations_and_not_found(tmp_path):
    app, client = _client(tmp_path)
    try:
        incidents = client.get("/api/incidents?status=open&severity=major").json()
        assert len(incidents) == 1
        incident_id = incidents[0]["id"]
        guidance = client.get(f"/api/incidents/{incident_id}/recommendations")
        assert guidance.status_code == 200
        assert len(guidance.json()["recommendations"]) >= 3
        assert client.get("/api/incidents?status=bogus").status_code == 422
        assert client.get("/api/incidents/9999").status_code == 404
        assert client.get("/api/incidents/9999/recommendations").status_code == 404
    finally:
        app.state.engine.dispose()


def test_acknowledge_resolve_lifecycle_and_validation(tmp_path):
    app, client = _client(tmp_path)
    try:
        incident_id = client.get("/api/incidents").json()[0]["id"]
        ack = client.post(
            f"/api/incidents/{incident_id}/acknowledge",
            json={"acknowledged_by": "Portfolio technician"},
        )
        assert ack.status_code == 200, ack.text
        assert ack.json()["status"] == "acknowledged"
        assert ack.json()["acknowledged_by"] == "Portfolio technician"
        resolved = client.post(f"/api/incidents/{incident_id}/resolve")
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["duration_seconds"] >= 0
        assert client.post(f"/api/incidents/{incident_id}/acknowledge", json={}).status_code == 409
        assert client.post("/api/incidents/9999/resolve").status_code == 404
        assert client.post("/api/incidents/9999/acknowledge", json={}).status_code == 404
        assert (
            client.post(
                f"/api/incidents/{incident_id}/acknowledge", json={"acknowledged_by": ""}
            ).status_code
            == 422
        )
    finally:
        app.state.engine.dispose()


def test_diagnosis_endpoint_simulated_and_live_gate(tmp_path):
    app, client = _client(tmp_path)
    try:
        simulated = client.post("/api/diagnose", json={"target": "example.com"})
        assert simulated.status_code == 200
        assert simulated.json()["mode"] == "simulated"
        assert simulated.json()["diagnosis"]["findings"]

        live = client.post(
            "/api/diagnose",
            json={"target": "example.com", "mode": "live"},
        )
        assert live.status_code == 403
        assert "NDM_ALLOW_LIVE_API=true" in live.json()["detail"]
    finally:
        app.state.engine.dispose()


def test_report_html_postmortem_and_metric_series(tmp_path):
    app, client = _client(tmp_path)
    try:
        html_report = client.get("/api/reports/html")
        assert html_report.status_code == 200
        assert html_report.headers["content-type"].startswith("text/html")
        assert "<!doctype html>" in html_report.text

        incidents = client.get("/api/incidents?status=resolved").json()
        assert len(incidents) == 1
        resolved_incident_id = incidents[0]["id"]
        resolved_postmortem = client.get(f"/api/incidents/{resolved_incident_id}/postmortem")
        assert resolved_postmortem.status_code == 200
        assert "Resolved" in resolved_postmortem.text

        incidents = client.get("/api/incidents").json()
        incident_id = incidents[0]["id"]
        postmortem = client.get(f"/api/incidents/{incident_id}/postmortem")
        assert postmortem.status_code == 200
        assert "## Summary" in postmortem.text

        devices = client.get("/api/devices").json()
        device_id = devices[0]["id"]
        series = client.get(f"/api/devices/{device_id}/metrics?limit=20")
        assert series.status_code == 200
        assert series.json()
        assert all("name" in item and "value" in item for item in series.json())

        assert client.get("/api/incidents/9999/postmortem").status_code == 404
    finally:
        app.state.engine.dispose()


def test_optional_api_key_protects_all_post_endpoints(tmp_path):
    app, client = _client(tmp_path)
    try:
        app.state.settings.api_key = "secret-key"
        incident_id = client.get("/api/incidents").json()[0]["id"]

        for path, body in (
            (f"/api/incidents/{incident_id}/acknowledge", {"acknowledged_by": "Operator"}),
            (f"/api/incidents/{incident_id}/resolve", {}),
            ("/api/diagnose", {"target": "example.com"}),
        ):
            missing = client.post(path, json=body)
            assert missing.status_code == 401
            wrong = client.post(path, json=body, headers={"X-API-Key": "wrong-key"})
            assert wrong.status_code == 401

        correct = client.post(
            "/api/diagnose",
            json={"target": "example.com"},
            headers={"X-API-Key": "secret-key"},
        )
        assert correct.status_code == 200

        app.state.settings.api_key = ""
        assert client.post("/api/diagnose", json={"target": "example.com"}).status_code == 200

        app.state.settings.api_key = None
        assert client.post(f"/api/incidents/{incident_id}/resolve", json={}).status_code == 200
    finally:
        app.state.engine.dispose()


def test_reports_and_dashboard_render(tmp_path):
    app, client = _client(tmp_path)
    try:
        assert (
            client.get("/api/reports/json").headers["content-type"].startswith("application/json")
        )
        assert (
            client.get("/api/reports/markdown").headers["content-type"].startswith("text/markdown")
        )
        assert client.get("/api/reports/csv").headers["content-type"].startswith("text/csv")
        assert client.get("/api/reports/xml").status_code == 422
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Network Diagnostics Monitor" in dashboard.text
        assert "/api/incidents" in dashboard.text
        assert "latency-chart" in dashboard.text
        assert "loss-chart" in dashboard.text
        assert "Device detail" in dashboard.text
        assert "Incident timeline" in dashboard.text
        assert "Diagnose a target" in dashboard.text
        assert "ndm-api-key" in dashboard.text
        assert "Resolved incidents" in dashboard.text
        assert "resolved-count" in dashboard.text
        assert "sessionStorage" in dashboard.text
        assert client.get("/dashboard").status_code == 200
        assert client.get("/docs").status_code == 200
    finally:
        app.state.engine.dispose()
