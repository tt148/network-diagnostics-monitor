# Network Diagnostics Monitor

[![CI](https://github.com/tt148/network-diagnostics-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/tt148/network-diagnostics-monitor/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A Python toolkit that runs network diagnostics, tracks incidents and explains common connectivity failures. It works on **simulated devices by default** and can check real, explicitly permitted targets in live mode.

## The problem it solves

Network problems usually arrive as vague symptoms: "the internet is slow" or "the site is down". This project shows a structured troubleshooting workflow, from reachability and DNS through to the application layer, with incident history, reports and clear next steps, while keeping a safe simulated mode for development and demonstrations.

## Features

- **DNS checks:** A, AAAA, CNAME, MX, NS and TXT lookups, resolution timing, NXDOMAIN, SERVFAIL and timeout detection, and a two-resolver comparison.
- **Latency and packet loss:** min, average, max, jitter and loss percentage using system `ping`, with an automatic TCP-connect fallback when ICMP is unavailable.
- **HTTP and TLS checks:** status code, response time, redirects, expected-status and keyword assertions, certificate validity and days until expiry.
- **Simulated monitoring data:** ten fictional devices with deterministic, seeded history and scripted failures (DNS outage, packet loss, HTTP 503, flapping, certificate nearing expiry).
- **Incident engine:** thresholds, severity, de-duplication, flapping detection and an open, acknowledged, resolved lifecycle.
- **Troubleshooting recommendations:** ordered, advisory steps for each incident type, with a rationale and a way to verify each step.
- **Reports:** JSON, Markdown and CSV exports of incidents and recommendations.
- **REST API and dashboard:** FastAPI with interactive OpenAPI docs, and a responsive dashboard that follows the system light or dark theme.
- **Safety by design:** allowlisted targets, blocked private and metadata ranges, bounded and rate-limited probes, no port scanning.

## Tech stack

Python 3.12, FastAPI, SQLAlchemy 2 (SQLite), Typer, dnspython, httpx, pydantic-settings, pytest, Ruff, Docker, GitHub Actions.

## Quick start

```bash
git clone https://github.com/tt148/network-diagnostics-monitor.git
cd network-diagnostics-monitor
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
cp .env.example .env

network-diagnostics diagnose example.com      # simulated, no network traffic
network-diagnostics seed                      # fictional devices, metrics and incidents
network-diagnostics incidents --status open
network-diagnostics recommendations 1
network-diagnostics report --format markdown
```

Start the API and dashboard:

```bash
uvicorn network_diagnostics_monitor.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> for the dashboard and <http://127.0.0.1:8000/docs> for the API documentation.

### Live checks (optional)

```bash
network-diagnostics diagnose example.com --mode live
```

Live mode only accepts targets listed in `NDM_ALLOWED_TARGETS`. Only check systems you own or are authorised to test.

### Docker

```bash
docker compose up --build -d
docker compose run --rm app network-diagnostics seed
```

The dashboard is published on `127.0.0.1:8000` only. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Tests and quality checks

These are the same checks CI runs:

```bash
ruff check .
ruff format --check .
pytest --cov=network_diagnostics_monitor --cov-report=term-missing --cov-fail-under=85
```

Tests are deterministic and never touch the network: DNS, HTTP, ping and sockets are mocked.

## Safety and scope

- Simulated mode is the default and sends no traffic.
- Live targets must be allowlisted. Private, link-local, multicast and cloud-metadata addresses are blocked unless lab ranges are explicitly enabled.
- Probes are sequential, bounded, time-limited and rate-limited.
- The allowlist is a permission boundary, not proof that a target is safe to probe.
- The API has no authentication yet, so keep it on localhost and do not deploy it publicly.

## Documentation

- [Architecture and data model](docs/ARCHITECTURE.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [Troubleshooting patterns](docs/TROUBLESHOOTING.md)
- [Security policy](SECURITY.md) and [contributing notes](CONTRIBUTING.md)

## Screenshots

Add real screenshots to `docs/screenshots/` and reference them here:

- `dashboard.png`: overview cards, device inventory and incident queue
- `incident-guidance.png`: troubleshooting guidance for an incident
- `api-docs.png`: the interactive API documentation

## Roadmap

- Per-device latency and loss charts, and a live "diagnose a target" panel on the dashboard
- Replayed incident history for seeded data, plus HTML reports and per-incident post-mortems
- Authentication for the API and write actions
- Scheduled live checks and notifications

## Why I built this

I wanted a project that connects day-to-day IT support work (triage, DNS and connectivity faults, clear communication) with solid software engineering: tested checks, a safe design, an API, containers and CI.

## License

MIT. See [LICENSE](LICENSE).
