# Network Diagnostics Monitor

A simulated-first network troubleshooting toolkit designed to demonstrate practical technical-support and networking skills. It combines DNS diagnostics, latency/loss measurements, HTTP/TLS checks, and explicit safeguards around live probes.

## Stage 1 status

Stage 1 implements the Python package scaffold, configuration, safety guardrails, simulated and live check engines, a `diagnose` CLI command, tests, and GitHub Actions CI. Later stages add persistence, incident handling, recommendations, reports, API, and dashboard.

## Safety and scope

- **Simulated mode is the default** and does not access the network.
- Live checks are restricted to `NDM_ALLOWED_TARGETS`; targets outside the list are rejected.
- Private, link-local, multicast, and metadata-service IP ranges are blocked unless lab ranges are explicitly enabled. Loopback is permitted only when explicitly allowlisted.
- No port scanning or traffic floods are implemented. Checks use hard timeouts, one probe at a time, and a process-local minimum interval.
- The allowlist is a permission boundary, not a guarantee that a target is safe to probe. Only use live mode on targets you are authorized to test.

## Quick start

Requires Python 3.12.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
network-diagnostics diagnose example.com
```

By default, this prints explicitly labelled simulated results. For a live check, use an allowlisted target and opt in:

```bash
network-diagnostics diagnose example.com --mode live
```

The CLI's live mode is subject to the allowlist, blocked-range policy, timeout, and rate limiter. The sample configuration includes `example.com`, `localhost`, `127.0.0.1`, `cloudflare-dns.com`, and `1.1.1.1`; adjust it only for targets you control or have permission to check.

## Development checks

These are the same checks used by CI:

```bash
ruff check .
ruff format --check .
pytest --cov=network_diagnostics_monitor --cov-report=term-missing --cov-fail-under=85
```

Tests use deterministic simulated data and mocks; they must not make real network requests.

## Architecture (Stage 1)

- `config.py`: typed environment settings.
- `safety.py`: target allowlisting, IP-range restrictions, and process-local rate limiting.
- `checks/`: DNS, latency/loss, and HTTP/TLS engines. Each supports simulated and live execution.
- `cli.py`: Typer command line entry point.

## Roadmap

1. **Stage 1:** safe diagnostics engines and CLI.
2. **Stage 2:** SQLite models, deterministic simulated devices/metrics, incident engine.
3. **Stage 3:** troubleshooting recommendations and report exports.
4. **Stage 4:** FastAPI, REST API, responsive dashboard.
5. **Stage 5:** containerization, complete operations documentation, deployment guide, architecture diagram.

## Screenshots

Screenshots will be added after the dashboard is implemented in Stage 4.

## Why I built this

Network issues are often reported as vague symptoms: “the internet is slow” or “the site is down.” This project is intended to show a structured troubleshooting workflow—from reachability and DNS through application-level checks—while keeping a safe simulated mode for development and demonstrations.
