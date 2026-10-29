"""Tests for layered diagnosis rules without network access."""

from network_diagnostics_monitor.diagnosis import diagnose_target


def _dns(status="ok", records=None, errors=None):
    return {"status": status, "records": records or {}, "errors": errors or {}}


def _latency(status="ok", received=3, sent=3, loss=0.0, jitter=1.0, average=20.0):
    return {
        "status": status,
        "probes_sent": sent,
        "probes_received": received,
        "packet_loss_percent": loss,
        "jitter_ms": jitter,
        "avg_ms": average,
    }


def _http(status_code=200, status="ok", tls_valid=True, days=90):
    return {
        "status_code": status_code,
        "status": status,
        "tls": {"valid": tls_valid, "days_until_expiry": days},
    }


def test_diagnosis_detects_dns_failure():
    result = diagnose_target(
        "name.example",
        _dns(status="error", errors={"A": "NXDOMAIN"}),
        _latency(received=0, loss=100.0),
        _http(status_code=None, status="error"),
    )
    assert result["findings"][0]["layer"] == "dns"
    assert result["findings"][0]["confidence"] == "high"
    assert "DNS A" in result["findings"][0]["evidence"][1]


def test_diagnosis_detects_unreachable_path():
    result = diagnose_target(
        "192.0.2.10",
        _dns(records={"A": ["192.0.2.10"]}),
        _latency(status="unreachable", received=0, loss=100.0, average=None),
        _http(status_code=None, status="error"),
    )
    layers = [finding["layer"] for finding in result["findings"]]
    assert "reachability" in layers


def test_diagnosis_detects_application_and_tls_rules():
    result = diagnose_target(
        "service.example",
        _dns(records={"A": ["192.0.2.20"]}),
        _latency(loss=2.0, jitter=5.0, average=30.0),
        _http(status_code=503, status="degraded", tls_valid=False, days=2),
    )
    layers = [finding["layer"] for finding in result["findings"]]
    assert "application" in layers
    assert "tls" in layers


def test_diagnosis_detects_expiring_certificate():
    result = diagnose_target(
        "secure.example",
        _dns(records={"A": ["192.0.2.30"]}),
        _latency(),
        _http(tls_valid=True, days=7),
    )
    tls = next(finding for finding in result["findings"] if finding["layer"] == "tls")
    assert tls["confidence"] == "high"


def test_diagnosis_detects_path_quality():
    result = diagnose_target(
        "gateway.example",
        _dns(records={"A": ["192.0.2.40"]}),
        _latency(loss=12.0, jitter=45.0, average=180.0),
        _http(),
    )
    finding = next(finding for finding in result["findings"] if finding["layer"] == "gateway")
    assert finding["confidence"] == "high"


def test_diagnosis_healthy_result_has_low_confidence_finding():
    result = diagnose_target(
        "example.com",
        _dns(records={"A": ["192.0.2.50"]}),
        _latency(),
        _http(),
    )
    assert result["findings"] == [
        {
            "layer": "application",
            "diagnosis": "No obvious network or application failure was detected by the available checks.",
            "confidence": "low",
            "evidence": [
                "DNS status: ok",
                "Latency probes received: 3/3",
                "HTTP status: 200",
            ],
            "next_steps": [
                "Repeat the check from the affected user or network segment.",
                "Compare application logs and historical baselines.",
                "Expand checks if the reported symptom is intermittent.",
            ],
        }
    ]
