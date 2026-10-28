You are a senior Python engineer. Build a complete, production-quality Network Diagnostic and Monitoring Platform as a portfolio project for technical support and networking roles. Work autonomously and in stages.

FIRST: save this entire message verbatim to docs/SPEC.md. Then build ONLY Stage 1 and stop. When I reply "continue", build the next stage. Never push to GitHub (I push myself).

STANDING RULES
- Python 3.12. Use ruff (lint + format) and pytest with pytest-cov. Run exactly what CI runs after every stage, fix your own errors, and show me the output.
- Conventional commits, one per meaningful feature (feat:, fix:, test:, docs:, chore:, ci:).
- Never commit secrets. Keep a .env.example. Use typed code, docstrings and small modules.
- SAFETY: live checks may only target an explicit allowlist in config (default: a few public test hosts such as example.com, a public DNS resolver, and localhost). Block private/link-local/metadata IP ranges by default (opt-in flag to allow lab ranges). No port scanning, no traffic floods: one probe at a time, hard timeouts, a minimum interval between checks. Default mode is SIMULATED, so tests and CI never touch the network.
- Be honest in the docs: simulated data is labelled as simulated; live mode only checks permitted targets.

PROJECT: "network-diagnostics-monitor"
Stack: FastAPI, SQLAlchemy 2 with SQLite, Jinja2 templates with a little vanilla JS (no frontend build step), Typer CLI, dnspython, httpx, pydantic settings, Docker + docker-compose, GitHub Actions CI.

CORE FEATURES
1. DNS checks: resolve A/AAAA/CNAME/MX/NS/TXT, measure resolution time, compare answers across two resolvers, detect NXDOMAIN, SERVFAIL, timeouts, and slow resolution.
2. Latency and packet loss: send N probes per target (ICMP via the system ping when permitted, with an automatic fallback to TCP connect timing), compute min/avg/max/jitter and loss %.
3. HTTP/HTTPS availability: status code, response time, redirects, TLS certificate expiry and validity, and keyword/expected-status assertions.
4. Simulated devices: a seed/scenario generator producing synthetic monitoring data for about 10 devices (router, core switch, access points, DNS server, web server, NAS, printer, VPN gateway) over several days, including realistic incidents: DNS outage, rising latency, packet loss on a link, HTTP 5xx errors, TLS certificate nearing expiry, flapping device, and a recovery. Deterministic via a random seed.
5. Incident engine: configurable thresholds create incidents (open, acknowledged, resolved) with severity, start/end time, duration and affected targets; de-duplicate repeated alerts; detect flapping.
6. Troubleshooting recommendations: a rules engine that maps symptoms to a likely cause and ordered fix steps, following a layered method (local link, gateway, IP reachability, DNS, application). Example: IP reachable but name fails means a DNS problem, so check the resolver config, try an alternate resolver, flush the cache. Each incident shows its diagnosis, confidence, and steps.
7. Dashboard (responsive, phone friendly, dark/light following the system): overview cards (devices up/down, open incidents, average latency, average loss), a device table with status, per-device latency/loss charts drawn as inline SVG, an incident timeline, and a "Diagnose a target" panel that runs live checks against allowlisted targets or simulated ones.
8. Reports: export incident history and device summaries as CSV and a self-contained HTML report; a Markdown "incident post-mortem" for any resolved incident (timeline, cause, fix, prevention).
9. REST API with OpenAPI docs (/docs): devices, checks, metrics, incidents, recommendations and reports. A CLI with commands such as: diagnose <target>, seed, run-checks, incidents, report.
10. Tests: unit tests for every checker (with mocked DNS/HTTP/ping), the incident engine, the recommendation rules, the report generators and the API; 85%+ coverage; all deterministic with no real network use.
11. Docs: README with a pitch, the real-world problem, a features list, an architecture diagram (hand-written SVG in docs/), a data model overview, setup with and without Docker, how to run tests, a safety and scope section, screenshots placeholders, a roadmap and a "Why I built this" section; MIT license, CONTRIBUTING-lite, SECURITY.md, a deployment guide for Render, and docs/TROUBLESHOOTING.md covering common connectivity failure patterns.

STAGES
Stage 1: project scaffold (src layout, config, pyproject, ruff, pytest, .env.example), the safety layer (allowlist, blocked ranges, rate limiting) and the three check engines (DNS, latency/loss, HTTP/TLS) with a simulated backend and a live backend, the Typer CLI "diagnose" command, tests, and GitHub Actions CI.
Stage 2: database models, the simulated-device scenario generator, metric storage, the incident engine and incident history.
Stage 3: the troubleshooting recommendations engine and the report generators (CSV, HTML, post-mortem).
Stage 4: the FastAPI app, REST API with OpenAPI docs, and the dashboard.
Stage 5: Docker and docker-compose, the full documentation set, the Render deployment guide, the architecture SVG, and a final summary with exact commands to push and a checklist of manual steps (screenshots, deploy, repo topics).

After each stage, give me: a 3-line summary, the test and coverage results, and anything you assumed. If you find a real bug, stop and tell me instead of silently working around it. Now save the spec and build Stage 1.