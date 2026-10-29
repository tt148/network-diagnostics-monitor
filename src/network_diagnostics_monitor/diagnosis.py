"""Rule-based diagnosis of combined DNS, reachability, and application results."""

from __future__ import annotations

import ipaddress
from typing import Any


def diagnose_target(
    target: str,
    dns: dict[str, Any],
    latency: dict[str, Any],
    http: dict[str, Any],
) -> dict[str, Any]:
    """Combine check results into ordered, layered findings without running probes."""
    findings: list[dict[str, Any]] = []

    dns_errors = dns.get("errors", {})
    dns_records = dns.get("records", {})
    a_records = dns_records.get("A", []) if isinstance(dns_records, dict) else []
    dns_failed = bool(dns_errors) or dns.get("status") in {"error"} or (
        not a_records and bool(dns_records) and target not in {str(address) for address in _ip_addresses(target)}
    )

    loss = float(latency.get("packet_loss_percent", 0.0) or 0.0)
    jitter = float(latency.get("jitter_ms", 0.0) or 0.0)
    average = latency.get("avg_ms")
    samples_received = int(latency.get("probes_received", 0) or 0)
    http_status = http.get("status_code")

    target_is_ip = bool(_ip_addresses(target))
    if dns_failed:
        diagnosis = "The target name cannot be resolved from the available DNS result."
        if target_is_ip:
            diagnosis = "The target IP is not being resolved through DNS, or DNS name resolution failed independently."
        findings.append(
            {
                "layer": "dns",
                "diagnosis": diagnosis,
                "confidence": "high",
                "evidence": [
                    f"DNS status: {dns.get('status', 'unknown')}",
                    *[f"DNS {record_type}: {message}" for record_type, message in dns_errors.items()],
                ],
                "next_steps": [
                    "Verify the hostname and configured search domains.",
                    "Query the same name against an approved DNS resolver.",
                    "Check resolver availability, ACLs, and DNS firewall rules.",
                ],
            }
        )

    if samples_received == 0:
        diagnosis = (
            "No probe reached the target; the path may fail at link, gateway, routing, or firewall layers."
        )
        findings.append(
            {
                "layer": "reachability",
                "diagnosis": diagnosis,
                "confidence": "high" if not dns_failed else "medium",
                "evidence": [
                    f"Latency status: {latency.get('status', 'unknown')}",
                    f"Probes received: {samples_received}/{latency.get('probes_sent', 0)}",
                ],
                "next_steps": [
                    "Check the local link, VLAN, default route, and gateway.",
                    "Verify routing and policy/firewall paths between the source and target.",
                    "Test reachability from the same segment and an adjacent network.",
                ],
            }
        )

    if loss >= 5.0 or jitter >= 20.0 or (average is not None and float(average) >= 150.0):
        evidence = [f"Packet loss: {loss:g}%", f"Jitter: {jitter:g} ms"]
        if average is not None:
            evidence.append(f"Average latency: {float(average):g} ms")
        findings.append(
            {
                "layer": "gateway" if loss >= 5.0 else "link",
                "diagnosis": "Path quality is degraded by loss, jitter, or elevated latency.",
                "confidence": "high" if loss >= 10.0 or jitter >= 40.0 else "medium",
                "evidence": evidence,
                "next_steps": [
                    "Measure again across multiple intervals to confirm the pattern.",
                    "Compare adjacent hops, gateways, and local-link counters.",
                    "Escalate sustained loss or jitter to the network owner for path remediation.",
                ],
            }
        )

    if isinstance(http_status, int) and http_status >= 500:
        findings.append(
            {
                "layer": "application",
                "diagnosis": "The target is reachable, but the application is returning a server error.",
                "confidence": "high",
                "evidence": [
                    f"HTTP status code: {http_status}",
                    f"HTTP status: {http.get('status', 'unknown')}",
                ],
                "next_steps": [
                    "Review application and reverse-proxy logs around the failing interval.",
                    "Check application health, dependencies, saturation, and recent deployments.",
                    "Verify a known-good endpoint and rollback or repair the failing service.",
                ],
            }
        )

    tls = http.get("tls", {})
    if isinstance(tls, dict) and tls.get("valid") is False:
        days = tls.get("days_until_expiry")
        findings.append(
            {
                "layer": "tls",
                "diagnosis": "TLS certificate validation failed.",
                "confidence": "high",
                "evidence": ["TLS validation result: invalid", *([f"Certificate error: {tls['error']}"] if tls.get("error") else [])],
                "next_steps": [
                    "Verify the certificate chain, hostname, trust store, and validity dates.",
                    "Renew or replace the certificate if it is expired or misconfigured.",
                    "Confirm the correct certificate is served by the application or load balancer.",
                ],
            }
        )
    elif isinstance(tls, dict) and isinstance(tls.get("days_until_expiry"), int):
        days = tls["days_until_expiry"]
        if days <= 14:
            findings.append(
                {
                    "layer": "tls",
                    "diagnosis": "The TLS certificate is nearing expiration.",
                    "confidence": "high" if days <= 7 else "medium",
                    "evidence": [f"Days until TLS expiry: {days}"],
                    "next_steps": [
                        "Confirm the active certificate and renewal automation.",
                        "Renew and deploy the replacement certificate before expiration.",
                        "Validate chain, hostname, and monitoring after deployment.",
                    ],
                }
            )

    if not findings:
        findings.append(
            {
                "layer": "application",
                "diagnosis": "No obvious network or application failure was detected by the available checks.",
                "confidence": "low",
                "evidence": [
                    f"DNS status: {dns.get('status', 'unknown')}",
                    f"Latency probes received: {samples_received}/{latency.get('probes_sent', 0)}",
                    f"HTTP status: {http_status if http_status is not None else http.get('status', 'unknown')}",
                ],
                "next_steps": [
                    "Repeat the check from the affected user or network segment.",
                    "Compare application logs and historical baselines.",
                    "Expand checks if the reported symptom is intermittent.",
                ],
            }
        )

    return {"target": target, "findings": findings}


def _ip_addresses(value: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        return (ipaddress.ip_address(value.split("://", 1)[-1].split("/", 1)[0]),)
    except ValueError:
        return ()
