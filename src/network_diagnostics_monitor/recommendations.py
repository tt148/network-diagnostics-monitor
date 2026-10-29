"""Actionable, safety-conscious troubleshooting guidance for known incident types."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Incident


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A troubleshooting action with a clear purpose and verification step."""

    action: str
    rationale: str
    verification: str
    priority: str = "recommended"


_GUIDANCE: dict[str, tuple[Recommendation, ...]] = {
    "device_unavailable": (
        Recommendation(
            "Confirm the device's power, link state, and maintenance status.",
            "The latest availability measurement indicates the device is down.",
            "Check the device status and compare with a second trusted monitoring source.",
            "urgent",
        ),
        Recommendation(
            "Check the directly connected cable, switch port, or wireless association.",
            "A local connectivity fault can make a device unreachable.",
            "Inspect interface/link indicators and recent interface error counters.",
        ),
        Recommendation(
            "Review recent configuration changes and neighboring-device incidents.",
            "A shared upstream failure or recent change may explain the outage.",
            "Correlate timestamps with change records and related alerts.",
        ),
    ),
    "high_latency": (
        Recommendation(
            "Compare latency at the endpoint and at successive network hops using approved diagnostics.",
            "This helps isolate whether delay is local, upstream, or service-side.",
            "Record several low-rate samples and compare them with the normal baseline.",
        ),
        Recommendation(
            "Review interface utilization, errors, and queue drops on the affected path.",
            "Congestion or interface faults can increase response time.",
            "Compare utilization and error counters over the same incident window.",
        ),
        Recommendation(
            "Check whether the destination service is under load.",
            "Application saturation can resemble a network problem.",
            "Compare host resource and application response-time metrics.",
        ),
    ),
    "packet_loss": (
        Recommendation(
            "Check interface error/discard counters and physical link health along the affected path.",
            "Loss may be caused by damaged links, congestion, or faulty interfaces.",
            "Compare counter deltas before and during the incident.",
        ),
        Recommendation(
            "Compare loss at multiple approved endpoints without increasing probe frequency.",
            "This helps distinguish a local issue from a wider path issue.",
            "Use a small number of time-bounded samples and retain timestamps.",
        ),
        Recommendation(
            "Review QoS, congestion, and recent network changes.",
            "Queue drops and policy changes can cause intermittent loss.",
            "Correlate policy/change timestamps with the observed loss.",
        ),
    ),
    "dns_degradation": (
        Recommendation(
            "Verify the configured DNS resolver and confirm that the affected hostname is correct.",
            "Resolver selection or a name typo can cause slow or failed lookups.",
            "Compare resolution against the approved resolver and a known-good hostname.",
        ),
        Recommendation(
            "Check resolver health, CPU/memory pressure, and upstream forwarding status.",
            "Resolver load or upstream delays can increase lookup time.",
            "Review resolver logs and upstream query latency for the incident window.",
        ),
        Recommendation(
            "Check for recent DNS record, forwarding, or network-policy changes.",
            "Recent changes may affect only selected names or clients.",
            "Compare current records and configuration with the last known-good state.",
        ),
    ),
    "http_error": (
        Recommendation(
            "Confirm the affected endpoint, response code, and whether a maintenance window is active.",
            "HTTP 5xx responses usually indicate a server-side or upstream-service problem.",
            "Repeat one request to the approved endpoint and capture status and timestamp.",
        ),
        Recommendation(
            "Review application logs, health checks, and upstream dependency status.",
            "The application or a dependency may be failing even when the host is reachable.",
            "Match request timestamps to server and dependency logs.",
        ),
        Recommendation(
            "Check recent deployments, load-balancer health, and capacity metrics.",
            "A release, unhealthy backend, or resource limit may explain the errors.",
            "Compare error rates before and after the latest change.",
        ),
    ),
    "tls_expiry": (
        Recommendation(
            "Confirm the certificate's actual expiry date and the hostname it covers.",
            "The recorded days remaining is a synthetic or monitored estimate that should be verified.",
            "Inspect the certificate through an approved client or certificate inventory.",
        ),
        Recommendation(
            "Identify the certificate owner and renewal procedure; schedule renewal before expiry.",
            "Early renewal avoids service interruption caused by an expired certificate.",
            "Confirm renewal, full chain, hostname match, and deployment to every relevant endpoint.",
            "urgent",
        ),
        Recommendation(
            "Check certificate automation and alerting for renewal failures.",
            "A failed renewal workflow can recur unless the underlying cause is fixed.",
            "Review automation logs and verify the next renewal is monitored.",
        ),
    ),
    "device_flapping": (
        Recommendation(
            "Check physical link stability, power, wireless signal, and interface error counters.",
            "Repeated up/down transitions can indicate an unstable link or device.",
            "Observe a bounded monitoring window and compare transition timestamps.",
        ),
        Recommendation(
            "Review spanning-tree, DHCP, wireless roaming, and port-security events where applicable.",
            "Network control-plane events can cause intermittent connectivity.",
            "Correlate event logs with each availability transition.",
        ),
        Recommendation(
            "Avoid repeated device reboots until logs and counters have been collected.",
            "A reboot can erase useful evidence and may worsen service impact.",
            "Preserve logs and follow the site's approved change and escalation process.",
        ),
    ),
}

_GENERIC = (
    Recommendation(
        "Validate the measurement and its timestamp against a second trusted source.",
        "A single observation can be stale or incomplete.",
        "Confirm the symptom with a recent independent measurement.",
    ),
    Recommendation(
        "Review recent changes and related device incidents.",
        "Correlated events can reveal a shared cause.",
        "Compare timestamps and document any common dependency.",
    ),
    Recommendation(
        "Escalate with the evidence collected if the issue persists.",
        "A clear handoff helps the next support tier act safely.",
        "Include affected asset, impact, timestamps, results, and actions already taken.",
    ),
)


def recommendations_for(incident: Incident) -> list[Recommendation]:
    """Return ordered troubleshooting actions for an incident, without making changes."""
    return list(_GUIDANCE.get(incident.kind, _GENERIC))


def recommendations_as_dicts(incident: Incident) -> list[dict[str, str]]:
    """Return recommendations in a JSON-serializable form."""
    return [
        {
            "action": item.action,
            "rationale": item.rationale,
            "verification": item.verification,
            "priority": item.priority,
        }
        for item in recommendations_for(incident)
    ]
