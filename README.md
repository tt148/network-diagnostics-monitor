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
- **Simulated monitoring data:** ten fictional devices with deterministic, seeded history, resolved DNS/latency/HTTP incidents with durations, several open VPN/TLS incidents, and replay that stays idempotent.
- **Incident engine:** replayed history, thresholds, severity, de-duplication, flapping detection and an open, acknowledged, resolved lifecycle.
- **Diagnosis engine:** DNS, reachability, path quality, application and TLS findings with confidence, evidence and ordered next steps.
- **Troubleshooting recommendations:** ordered, advisory steps for each incident type, with a rationale and a way to verify each step.
- **Reports:** self-contained HTML, incident Markdown post-mortems, per-device CSV summaries, formula-safe CSV exports, and JSON/Markdown reports.
- **REST API and dashboard:** diagnosis and report endpoints, optional POST API-key protection, and a responsive inline-SVG dashboard with device detail, incident timeline, latency/loss charts and diagnosis controls.
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
network-diagnostics incidents --status open   # current VPN/TLS incidents stay open
network-diagnostics incidents --status resolved
network-diagnostics recommendations 1
network-diagnostics report --format markdown
network-diagnostics report --format html --output report.html
network-diagnostics report --format postmortem --incident-id 1 --output postmortem.md
network-diagnostics report --format device-csv --output devices.csv
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
- POST lifecycle and diagnosis endpoints can use `X-API-Key` when `NDM_API_KEY` is configured; public deployments must set a strong key.
- Live API diagnosis is disabled unless `NDM_ALLOW_LIVE_API=true`, and live targets still require the existing allowlist and safety checks.

## Documentation

- [Architecture and data model](docs/ARCHITECTURE.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [Troubleshooting patterns](docs/TROUBLESHOOTING.md)
- [Security policy](SECURITY.md) and [contributing notes](CONTRIBUTING.md)

## Roadmap

- Scheduled live checks and notifications

## Why I built this

I wanted a project that connects day-to-day IT support work (triage, DNS and connectivity faults, clear communication) with solid software engineering: tested checks, a safe design, an API, containers and CI.

## License

MIT. See [LICENSE](LICENSE).
