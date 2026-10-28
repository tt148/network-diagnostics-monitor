"""HTTP availability and TLS certificate checks."""

from __future__ import annotations

import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from ..safety import RateLimiter, SafetyError, resolve_host_safely, validate_live_target


def check_http(
    target: str,
    *,
    mode: str = "simulated",
    settings: Settings | None = None,
    expected_status: int | None = 200,
    keyword: str | None = None,
    limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Check one HTTP(S) URL for availability, redirects, and TLS metadata."""
    settings = settings or Settings()
    url = target if "://" in target else f"https://{target}"
    if mode == "simulated":
        simulated_status = 200
        simulated_body = "Simulated example response for network diagnostics."
        status_ok = expected_status is None or simulated_status == expected_status
        keyword_ok = keyword is None or keyword.casefold() in simulated_body.casefold()
        return {
            "target": url,
            "mode": "simulated",
            "status": "ok" if status_ok and keyword_ok else "degraded",
            "status_code": simulated_status,
            "duration_ms": 43.1,
            "redirects": [],
            "tls": {"valid": True, "days_until_expiry": 90, "simulated": True},
            "assertions": {"expected_status": status_ok, "keyword": keyword_ok if keyword else None},
            "message": "SIMULATED: no HTTP request or TLS handshake was made.",
        }
    if mode != "live":
        raise ValueError("mode must be 'simulated' or 'live'")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SafetyError("Only valid HTTP(S) targets are supported.")
    hostname = validate_live_target(parsed.hostname, settings)
    resolve_host_safely(hostname, settings, settings.timeout_seconds)
    (limiter or RateLimiter(settings.min_check_interval_seconds)).wait_turn()
    started = time.perf_counter()
    try:
        with httpx.Client(
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            verify=True,
            max_redirects=5,
        ) as client:
            response = client.get(url)
    except httpx.TimeoutException as exc:
        return {
            "target": url, "mode": "live", "status": "timeout", "status_code": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "redirects": [], "tls": {"valid": None, "days_until_expiry": None},
            "assertions": {}, "error": str(exc),
        }
    except httpx.HTTPError as exc:
        return {
            "target": url, "mode": "live", "status": "error", "status_code": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "redirects": [], "tls": {"valid": False, "days_until_expiry": None},
            "assertions": {}, "error": str(exc),
        }

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    history = [{"status_code": item.status_code, "url": str(item.url)} for item in response.history]
    if response.is_redirect and response.headers.get("location"):
        history.append({"status_code": response.status_code, "url": response.headers["location"]})
    status_ok = expected_status is None or response.status_code == expected_status
    keyword_ok = keyword is None or keyword.casefold() in response.text.casefold()
    tls_info: dict[str, Any] = {"valid": parsed.scheme != "https", "days_until_expiry": None}
    if parsed.scheme == "https":
        tls_info = _inspect_tls(hostname, parsed.port or 443, settings.timeout_seconds)
    result_status = "ok" if status_ok and keyword_ok else "degraded"
    return {
        "target": url,
        "mode": "live",
        "status": result_status,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "redirects": history,
        "tls": tls_info,
        "assertions": {"expected_status": status_ok, "keyword": keyword_ok if keyword else None},
        "message": "Live HTTP result; target passed the configured allowlist and safety checks.",
    }


def _inspect_tls(hostname: str, port: int, timeout: float) -> dict[str, Any]:
    """Read peer certificate expiry and validate its chain/hostname."""
    context = ssl.create_default_context()
    valid = False
    days_until_expiry: int | None = None
    error: str | None = None
    try:
        with socket.create_connection((hostname, port), timeout=timeout) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
                certificate = tls_socket.getpeercert()
                not_after = certificate.get("notAfter")
                if not_after:
                    expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                    days_until_expiry = (expires - datetime.now(timezone.utc)).days
                valid = True
    except (OSError, ssl.SSLError, ValueError) as exc:
        error = str(exc)
    result: dict[str, Any] = {"valid": valid, "days_until_expiry": days_until_expiry}
    if error:
        result["error"] = error
    return result
