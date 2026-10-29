"""HTTP/TLS checker tests without real HTTP calls."""

from typing import ClassVar

import pytest

from network_diagnostics_monitor.checks.http import check_http


def test_simulated_http_result(settings) -> None:
    result = check_http("example.com", settings=settings, keyword="example")
    assert result["mode"] == "simulated"
    assert result["status_code"] == 200
    assert result["tls"]["valid"] is True
    assert result["assertions"]["keyword"] is True
    assert "no HTTP request" in result["message"]


def test_simulated_http_keyword_assertion(settings) -> None:
    result = check_http("example.com", settings=settings, keyword="missing")
    assert result["assertions"]["keyword"] is False
    assert result["status"] == "degraded"


def test_expected_non_2xx_status_can_pass_assertion(monkeypatch, settings, limiter) -> None:
    import network_diagnostics_monitor.checks.http as http_check

    class FakeResponse:
        status_code = 503
        text = "maintenance"
        history: ClassVar[list] = []
        headers: ClassVar[dict] = {}
        is_success = False
        is_redirect = False
        url = "https://example.com"

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        http_check, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"]
    )
    monkeypatch.setattr(http_check.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        http_check, "_inspect_tls", lambda *args: {"valid": True, "days_until_expiry": 50}
    )
    result = check_http(
        "https://example.com", mode="live", settings=settings, expected_status=503, limiter=limiter
    )
    assert result["status"] == "ok"
    assert result["assertions"]["expected_status"] is True


def test_live_http_rejects_non_allowlisted_target(settings) -> None:
    with pytest.raises(ValueError, match="not in NDM_ALLOWED_TARGETS"):
        check_http("https://not-allowed.invalid", mode="live", settings=settings)


def test_invalid_scheme_rejected(settings) -> None:
    with pytest.raises(ValueError, match="HTTP"):
        check_http("ftp://example.com", mode="live", settings=settings)


def test_live_http_success_and_keyword(monkeypatch, settings, limiter) -> None:
    import network_diagnostics_monitor.checks.http as http_check

    class FakeResponse:
        status_code = 200
        text = "hello expected phrase"
        history: ClassVar[list] = []
        headers: ClassVar[dict] = {}
        is_success = True
        is_redirect = False
        url = "https://example.com"

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        http_check, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"]
    )
    monkeypatch.setattr(http_check.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        http_check, "_inspect_tls", lambda *args: {"valid": True, "days_until_expiry": 50}
    )
    result = check_http(
        "https://example.com",
        mode="live",
        settings=settings,
        keyword="expected phrase",
        limiter=limiter,
    )
    assert result["status"] == "ok"
    assert result["assertions"] == {"expected_status": True, "keyword": True}
    assert result["tls"]["valid"] is True


def test_live_http_redirect_is_reported_not_followed(monkeypatch, settings, limiter) -> None:
    import network_diagnostics_monitor.checks.http as http_check

    class FakeResponse:
        status_code = 302
        text = ""
        history: ClassVar[list] = []
        headers: ClassVar[dict] = {"location": "https://other.example/"}
        is_success = False
        is_redirect = True
        url = "https://example.com"

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        http_check, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"]
    )
    monkeypatch.setattr(http_check.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        http_check, "_inspect_tls", lambda *args: {"valid": True, "days_until_expiry": 50}
    )
    result = check_http("https://example.com", mode="live", settings=settings, limiter=limiter)
    assert result["status_code"] == 302
    assert result["redirects"][0]["url"] == "https://other.example/"


def test_live_http_timeout(monkeypatch, settings, limiter) -> None:
    import httpx

    import network_diagnostics_monitor.checks.http as http_check

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(
        http_check, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"]
    )
    monkeypatch.setattr(http_check.httpx, "Client", FakeClient)
    result = check_http("https://example.com", mode="live", settings=settings, limiter=limiter)
    assert result["status"] == "timeout"
    assert result["status_code"] is None


def test_live_http_connection_error(monkeypatch, settings, limiter) -> None:
    import httpx

    import network_diagnostics_monitor.checks.http as http_check

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(
        http_check, "resolve_host_safely", lambda *args, **kwargs: ["93.184.216.34"]
    )
    monkeypatch.setattr(http_check.httpx, "Client", FakeClient)
    result = check_http("https://example.com", mode="live", settings=settings, limiter=limiter)
    assert result["status"] == "error"
    assert result["tls"]["valid"] is False


def test_live_http_invalid_url_rejected(settings) -> None:
    import pytest

    from network_diagnostics_monitor.safety import SafetyError

    with pytest.raises(SafetyError, match="HTTP"):
        check_http("ftp://example.com", mode="live", settings=settings)
