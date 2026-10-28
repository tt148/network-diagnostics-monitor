"""DNS checker tests are simulated and therefore network-free."""

import pytest

from network_diagnostics_monitor.checks.dns import check_dns


def test_simulated_dns_has_all_record_types(settings) -> None:
    result = check_dns("example.com", settings=settings)
    assert result["mode"] == "simulated"
    assert result["status"] == "ok"
    assert set(result["records"]) == {"A", "AAAA", "CNAME", "MX", "NS", "TXT"}
    assert "no DNS request" in result["message"]


def test_live_dns_rejects_non_allowlisted_target(settings) -> None:
    with pytest.raises(ValueError, match="not in NDM_ALLOWED_TARGETS"):
        check_dns("not-allowed.invalid", mode="live", settings=settings)


def test_invalid_record_type_fails_in_live_mode(settings, limiter) -> None:
    with pytest.raises(ValueError, match="Unsupported DNS record"):
        check_dns("example.com", mode="live", settings=settings, record_types=("BOGUS",), limiter=limiter)


def test_unknown_mode_rejected(settings) -> None:
    with pytest.raises(ValueError, match="mode"):
        check_dns("example.com", mode="other", settings=settings)


def test_live_dns_success_and_comparison(monkeypatch, settings, limiter) -> None:
    import dns.resolver

    class Record:
        def to_text(self):
            return "93.184.216.34"

        def __str__(self):
            return "93.184.216.34"

    class Answer:
        def __iter__(self):
            return iter([Record()])

    class FakeResolver:
        def __init__(self, *args, **kwargs):
            self.nameservers = []
            self.timeout = 0
            self.lifetime = 0

        def resolve(self, hostname, record_type, lifetime=None):
            return Answer()

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)
    result = check_dns("example.com", mode="live", settings=settings, limiter=limiter,
                       record_types=("A",))
    assert result["mode"] == "live"
    assert result["status"] == "ok"
    assert result["records"]["A"] == ["93.184.216.34"]
    assert result["resolver_comparison"] == {"1.1.1.1": "match", "8.8.8.8": "match"}


def test_live_dns_nxdomain(monkeypatch, settings, limiter) -> None:
    import dns.resolver

    class FakeResolver:
        def __init__(self, *args, **kwargs):
            self.nameservers = []
            self.timeout = 0
            self.lifetime = 0

        def resolve(self, hostname, record_type, lifetime=None):
            raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)
    result = check_dns("example.com", mode="live", settings=settings, limiter=limiter,
                       record_types=("A",))
    assert result["status"] == "error"
    assert result["errors"]["A"] == "NXDOMAIN"


def test_live_dns_no_answer_and_servfail(monkeypatch, settings, limiter) -> None:
    import dns.resolver

    class FakeResolver:
        def __init__(self, *args, **kwargs):
            self.nameservers = []
            self.timeout = 0
            self.lifetime = 0

        def resolve(self, hostname, record_type, lifetime=None):
            if self.nameservers:
                raise dns.resolver.NoNameservers()
            if record_type == "A":
                raise dns.resolver.NoAnswer()
            raise dns.resolver.NoNameservers()

    monkeypatch.setattr(dns.resolver, "Resolver", FakeResolver)
    result = check_dns("example.com", mode="live", settings=settings, limiter=limiter,
                       record_types=("A", "AAAA"))
    assert result["records"]["A"] == []
    assert result["errors"]["AAAA"] == "SERVFAIL"
    assert result["resolver_comparison"]["1.1.1.1"] == "NONAMESERVERS"
