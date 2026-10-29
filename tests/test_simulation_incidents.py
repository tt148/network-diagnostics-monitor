"""Tests for persistence, the metric simulator, and the incident engine."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from network_diagnostics_monitor.database import create_schema, make_engine, make_session_factory
from network_diagnostics_monitor.incidents import (
    acknowledge_incident,
    evaluate_incidents,
    incident_duration_seconds,
    resolve_incident,
)
from network_diagnostics_monitor.models import Device, Incident, Metric
from network_diagnostics_monitor.simulation import generate_metrics, seed_devices


@pytest.fixture
def session():
    engine = make_engine("sqlite:///:memory:")
    create_schema(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_seed_creates_ten_fictional_devices(session):
    devices = seed_devices(session)
    session.commit()
    assert len(devices) == 10
    assert session.scalar(select(Device).where(Device.is_simulated.is_(False))) is None
    assert len(session.scalars(select(Device)).all()) == 10


def test_seed_is_idempotent(session):
    seed_devices(session)
    seed_devices(session)
    session.commit()
    assert len(session.scalars(select(Device)).all()) == 10


def test_metrics_are_deterministic_and_idempotent(session):
    end = datetime(2026, 10, 20, tzinfo=UTC)
    inserted = generate_metrics(session, days=1, interval_minutes=360, seed=7, end_time=end)
    session.commit()
    count_before = len(session.scalars(select(Metric)).all())
    inserted_again = generate_metrics(session, days=1, interval_minutes=360, seed=7, end_time=end)
    session.commit()
    assert inserted == 10 * 6 * 5
    assert inserted_again == 0
    assert len(session.scalars(select(Metric)).all()) == count_before


def test_invalid_simulation_ranges_rejected(session):
    with pytest.raises(ValueError, match="days"):
        generate_metrics(session, days=0)
    with pytest.raises(ValueError, match="interval_minutes"):
        generate_metrics(session, interval_minutes=1)


def _add_metric(session, device, name, value, recorded_at):
    metric = Metric(
        device_id=device.id,
        name=name,
        value=value,
        unit="ms" if name.endswith("_ms") else "%",
        status="critical",
        recorded_at=recorded_at,
        source="test",
    )
    session.add(metric)
    session.flush()
    return metric


def test_incident_detection_deduplicates_and_resolves(session):
    device = seed_devices(session)[0]
    first = datetime(2026, 1, 1, tzinfo=UTC)
    _add_metric(session, device, "latency_ms", 180, first)
    found = evaluate_incidents(session)
    session.commit()
    assert len(found) == 1
    incident = session.scalar(select(Incident).where(Incident.kind == "high_latency"))
    assert incident is not None and incident.status == "open"

    _add_metric(session, device, "latency_ms", 220, first + timedelta(minutes=5))
    evaluate_incidents(session)
    session.commit()
    assert len(session.scalars(select(Incident).where(Incident.kind == "high_latency")).all()) == 1
    assert incident.occurrence_count == 2

    _add_metric(session, device, "latency_ms", 20, first + timedelta(minutes=10))
    evaluate_incidents(session)
    session.commit()
    assert incident.status == "resolved"
    assert incident.duration_seconds == 600


def test_incident_acknowledge_and_manual_resolution(session):
    device = seed_devices(session)[0]
    start = datetime(2026, 2, 1, tzinfo=UTC)
    incident = Incident(
        device_id=device.id, kind="manual", title="Manual test", severity="warning",
        started_at=start, last_observed_at=start,
    )
    session.add(incident)
    session.commit()
    acknowledge_incident(session, incident.id, "  Sam  ", now=start + timedelta(minutes=1))
    assert incident.status == "acknowledged"
    assert incident.acknowledged_by == "Sam"
    resolve_incident(session, incident.id, now=start + timedelta(minutes=7))
    assert incident.status == "resolved"
    assert incident.duration_seconds == 420
    with pytest.raises(ValueError, match="resolved"):
        acknowledge_incident(session, incident.id, "Sam")


def test_missing_incident_and_blank_acknowledger_rejected(session):
    with pytest.raises(ValueError, match="not found"):
        resolve_incident(session, 999)
    device = seed_devices(session)[0]
    incident = Incident(device_id=device.id, kind="manual", title="Manual")
    session.add(incident)
    session.commit()
    with pytest.raises(ValueError, match="blank"):
        acknowledge_incident(session, incident.id, "  ")


def test_flapping_detected_from_availability_transitions(session):
    device = seed_devices(session)[0]
    start = datetime(2026, 3, 1, tzinfo=UTC)
    for index, value in enumerate([1, 0, 1, 0, 1, 0, 1]):
        _add_metric(session, device, "availability", float(value), start + timedelta(minutes=index))
    evaluate_incidents(session, flapping_window=12, flapping_transitions=4)
    session.commit()
    incident = session.scalar(select(Incident).where(Incident.kind == "device_flapping"))
    assert incident is not None
    assert incident.is_flapping is True


def test_incident_duration_for_active_incident(session):
    device = seed_devices(session)[0]
    start = datetime(2026, 4, 1, tzinfo=UTC)
    incident = Incident(device_id=device.id, kind="manual", title="Active", started_at=start)
    session.add(incident)
    session.commit()
    assert incident_duration_seconds(incident, now=start + timedelta(seconds=90)) == 90


def test_threshold_override_and_availability_incident(session):
    device = seed_devices(session)[0]
    now = datetime(2026, 5, 1, tzinfo=UTC)
    _add_metric(session, device, "latency_ms", 90, now)
    evaluate_incidents(session, thresholds={"latency_ms": 80})
    session.commit()
    incident = session.scalar(select(Incident).where(Incident.kind == "high_latency"))
    assert incident is not None
    assert incident.severity == "warning"

    _add_metric(session, device, "availability", 0.0, now + timedelta(minutes=1))
    evaluate_incidents(session)
    session.commit()
    assert session.scalar(select(Incident).where(Incident.kind == "device_unavailable")) is not None


def test_dns_http_and_tls_threshold_classification(session):
    device = seed_devices(session)[0]
    now = datetime(2026, 6, 1, tzinfo=UTC)
    _add_metric(session, device, "dns_resolution_ms", 1800, now)
    _add_metric(session, device, "http_status", 503, now)
    _add_metric(session, device, "tls_days_remaining", 2, now)
    evaluate_incidents(session)
    session.commit()
    by_kind = {i.kind: i for i in session.scalars(select(Incident)).all()}
    assert by_kind["dns_degradation"].severity == "critical"
    assert by_kind["http_error"].severity == "critical"
    assert by_kind["tls_expiry"].severity == "critical"


def test_flapping_incident_resolves_when_history_stabilizes(session):
    device = seed_devices(session)[0]
    start = datetime(2026, 7, 1, tzinfo=UTC)
    for index, value in enumerate([1, 0, 1, 0, 1, 0]):
        _add_metric(session, device, "availability", float(value), start + timedelta(minutes=index))
    evaluate_incidents(session, flapping_window=12, flapping_transitions=4, now=start)
    session.commit()
    incident = session.scalar(select(Incident).where(Incident.kind == "device_flapping"))
    assert incident is not None
    _add_metric(session, device, "availability", 1.0, start + timedelta(minutes=10))
    _add_metric(session, device, "availability", 1.0, start + timedelta(minutes=11))
    evaluate_incidents(session, flapping_window=4, flapping_transitions=3, now=start + timedelta(minutes=12))
    session.commit()
    assert incident.status == "resolved"


def test_sqlite_file_database_and_foreign_key_support(tmp_path):
    from network_diagnostics_monitor.database import make_engine

    engine = make_engine(f"sqlite:///{tmp_path / 'monitor.db'}")
    create_schema(engine)
    assert (tmp_path / "monitor.db").exists()
    engine.dispose()
