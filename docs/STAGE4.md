# Stage 4 — API and dashboard

## Scope

Stage 4 adds a FastAPI application and a responsive dashboard for viewing persisted monitoring data. It preserves the simulated-first model and does not add network probes to the API.

## Run locally

```bash
python -m pip install -e ".[dev]"
network-diagnostics seed
uvicorn network_diagnostics_monitor.api:app --host 127.0.0.1 --port 8000
```

Open the dashboard at <http://127.0.0.1:8000/>, interactive OpenAPI docs at <http://127.0.0.1:8000/docs>, or ReDoc at <http://127.0.0.1:8000/redoc>.

The API and CLI read the database selected by `NDM_DATABASE_URL`; the default is `sqlite:///./network_diagnostics.db`. Keep the server bound to loopback for local demonstrations. The current application does not provide authentication, role-based authorization, CSRF protections for a public deployment, or HTTPS termination. Do not expose it to an untrusted network before adding those controls and deploying behind a hardened ASGI server/reverse proxy.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health status |
| GET | `/api/summary` | Device, metric, incident, status, and severity counts |
| GET | `/api/devices` | Device inventory |
| GET | `/api/devices/{device_id}` | One device |
| GET | `/api/devices/{device_id}/metrics` | Recent metrics for a device |
| GET | `/api/metrics` | Recent metrics across devices |
| GET | `/api/incidents` | Filterable incident queue |
| GET | `/api/incidents/{incident_id}` | Incident details |
| POST | `/api/incidents/{incident_id}/acknowledge` | Acknowledge an incident |
| POST | `/api/incidents/{incident_id}/resolve` | Resolve an incident |
| GET | `/api/incidents/{incident_id}/recommendations` | Advisory troubleshooting steps |
| GET | `/api/reports/{json\|markdown\|csv}` | Export persisted report data |

List endpoints enforce a maximum `limit` of 500. Unknown records return 404; invalid query parameters return 422. Acknowledging an already resolved incident returns 409. The API does not allow creating devices, writing metrics, changing target allowlists, or initiating diagnostic probes.

## Dashboard

The root path `/` and `/dashboard` serve the dashboard. It displays summary cards, inventory, the incident queue, and latest measurements. Technicians can acknowledge or resolve incidents and open advisory guidance. It uses same-origin API requests and does not load scripts, fonts, or styles from third-party CDNs.

## Verification

The Stage 4 tests use a temporary SQLite database and FastAPI's in-process test client. They cover summary and inventory, metric limits, incident filters, recommendation lookup, lifecycle transitions, report media types, dashboard rendering, and expected error responses. Tests do not contact monitored hosts.
