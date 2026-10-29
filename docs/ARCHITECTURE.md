# Architecture

Network Diagnostics Monitor is a small, layered Python application. Everything runs in **simulated mode** by default; live checks are opt-in and restricted to an explicit allowlist.

![Architecture diagram](images/architecture.svg)

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Typed settings read from `NDM_*` environment variables (pydantic-settings). |
| `safety.py` | Target allowlist, blocked IP ranges (private, link-local, multicast, cloud metadata, IPv4-mapped IPv6), safe DNS resolution and a process-local rate limiter. |
| `checks/dns.py` | DNS record checks (A, AAAA, CNAME, MX, NS, TXT), timing, and a two-resolver comparison. |
| `checks/latency.py` | Latency, jitter and packet loss using system `ping`, with a TCP-connect fallback when ICMP is unavailable. |
| `checks/http.py` | HTTP availability, redirects, expected status and keyword assertions, and TLS certificate expiry. |
| `models.py`, `database.py` | SQLAlchemy 2 models (`Device`, `Metric`, `Incident`), SQLite-first engine and sessions. |
| `simulation.py` | Ten fictional devices and a deterministic, seeded metric generator with scripted failure scenarios. |
| `incidents.py` | Threshold evaluation, de-duplication, severity, flapping detection and the incident lifecycle. |
| `recommendations.py` | Advisory troubleshooting steps keyed by incident type. |
| `reports.py` | JSON, Markdown and CSV reports built from persisted data. |
| `api.py` | FastAPI application, REST endpoints and the dashboard page. |
| `cli.py` | Typer command line interface. |

## Data model

- **Device**: a fictional or explicitly configured asset (name, type, hostname, location, simulated flag).
- **Metric**: a timestamped measurement (name, value, unit, status, source, details). A compound index supports device, metric and time queries.
- **Incident**: kind, severity, lifecycle status (`open`, `acknowledged`, `resolved`), start, acknowledgement and resolution timestamps, duration, occurrence count and a flapping flag.

The schema is created with SQLAlchemy `create_all`; there is no migration tooling yet. Set `NDM_DATABASE_URL` to use another database.

## Simulation

`network-diagnostics seed` creates ten fictional devices and generates deterministic metric history (default: three days, hourly) from a fixed random seed. Re-running the same window does not duplicate rows. The scripted scenarios are:

- DNS outage on the DNS server
- High latency and packet loss on the edge router and VPN gateway
- HTTP 503 responses on the web server
- Intermittent availability on an access point (flapping)
- A synthetic TLS certificate close to expiry

All generated rows carry the source `simulation`. No network traffic is produced.

## Incident engine

Default thresholds live in `incidents.DEFAULT_THRESHOLDS` and can be overridden programmatically. Active (`open` or `acknowledged`) incidents are de-duplicated per device and kind; repeated abnormal readings increase `occurrence_count`. A healthy latest reading resolves the active incident and records its duration. Flapping is detected from up/down transitions in the most recent availability samples.

## Recommendations and reports

Recommendations are transparent rules, not an automated root-cause engine: each incident type maps to ordered actions with a rationale and a way to verify the result. They are advisory and never change configuration or run probes.

Reports can be rendered as JSON, Markdown (summary table plus recommendations) or CSV (one row per incident).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health status |
| GET | `/api/summary` | Device, metric and incident counts |
| GET | `/api/devices`, `/api/devices/{id}` | Device inventory |
| GET | `/api/devices/{id}/metrics`, `/api/metrics` | Recent measurements |
| GET | `/api/incidents`, `/api/incidents/{id}` | Filterable incident queue |
| POST | `/api/incidents/{id}/acknowledge` | Acknowledge an incident |
| POST | `/api/incidents/{id}/resolve` | Resolve an incident |
| GET | `/api/incidents/{id}/recommendations` | Advisory troubleshooting steps |
| GET | `/api/reports/{json,markdown,csv}` | Export report data |

List endpoints cap `limit` at 500. Unknown records return 404, invalid query parameters 422, and acknowledging a resolved incident 409. The API does not create devices, write metrics, change the allowlist or start probes. Interactive documentation is served at `/docs` and `/redoc`.

## Dashboard

The dashboard (`/`) uses plain HTML, CSS and JavaScript with no external CDN. It shows summary cards, the device inventory, the incident queue (with acknowledge, resolve and guidance actions) and the latest measurements. It follows the system light or dark theme and works on phone screens.

## Safety model

- Simulated mode is the default and never touches the network.
- Live targets must be listed in `NDM_ALLOWED_TARGETS`.
- Private, link-local, multicast, reserved and cloud-metadata addresses are blocked unless `NDM_ALLOW_LAB_RANGES=true`; loopback is allowed only when explicitly allowlisted. DNS answers are re-checked before connecting.
- Probes are sequential, bounded (1 to 5 per check), time-limited and rate-limited. There is no port scanning.
- HTTP checks do not follow redirects, so a redirect cannot lead outside the allowlist.

## Known limitations

- The API has no authentication or CSRF protection; keep it local (see [DEPLOYMENT.md](DEPLOYMENT.md)).
- Incident evaluation looks at each device's latest measurement, so seeded data produces the current incidents but not a replayed history of past, resolved ones.
- The dashboard has no charts and no live "diagnose a target" panel yet; the diagnostic engines are available through the CLI.
- Reports are available as JSON, Markdown and CSV; there is no HTML report or per-incident post-mortem yet.
- No scheduler or notification delivery.
- The Docker image and Compose file have not been built in the environment where they were written; run `docker compose build` and confirm `/api/health` before relying on them.
