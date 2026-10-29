# Deployment and operations guide

This guide covers local development, a reproducible Docker deployment, data persistence, backups, and an optional Render demonstration. The application is a portfolio/demo system, not a hardened multi-user monitoring service.

## Before you deploy

- Use Python 3.12 for the project's target runtime.
- Keep `NDM_MODE=simulated` unless you have a documented need for live checks and have configured an explicit target allowlist.
- Do not commit `.env`, database files, credentials, real device inventories, or exported reports containing sensitive data.
- The current API does **not** implement authentication, authorization, or CSRF protection for state-changing browser requests. Do not expose it publicly or put sensitive operational data into it. A public deployment should wait until those controls and a proper production security review exist.
- The SQLite database is appropriate for this single-instance demonstration. It is not a substitute for managed, concurrent production storage.

## Option A: run locally without Docker

From the repository root, create and activate a virtual environment, then install the package:

```bash
python3.12 -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
network-diagnostics seed
uvicorn network_diagnostics_monitor.api:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/` for the dashboard or `http://127.0.0.1:8000/docs` for interactive API documentation. Stop the server with Ctrl+C. The default SQLite file is `./network_diagnostics.db`; set `NDM_DATABASE_URL` to use another SQLAlchemy database URL.

## Option B: Docker Compose

Install Docker Engine with the Compose plugin, or Docker Desktop. From the repository root:

```bash
docker compose build
docker compose up -d
# Seed the persistent database with fictional sample devices and metrics
docker compose run --rm app network-diagnostics seed
# Inspect startup and health
docker compose ps
docker compose logs app
```

Open `http://127.0.0.1:8000/`. The compose file binds the port to loopback only, runs as a non-root user, uses a read-only container filesystem apart from temporary storage and the database volume, enables `no-new-privileges`, and configures a health check. The `ndm-data` named volume persists SQLite data across container recreation.

Useful operations:

```bash
# Follow logs
docker compose logs -f app
# Stop without deleting data
docker compose down
# Rebuild after changing source
docker compose up --build -d
# Remove the container and persistent data (DESTRUCTIVE)
docker compose down -v
```

The last command permanently deletes the named database volume. Back it up first if you need to keep the data.

### Backup and restore the SQLite database

Stop writes before taking a simple file-level backup. With the default Compose volume, one practical approach is to use a temporary container that mounts the same volume and copies the database to a host-mounted backup directory. Create `./backups` first, then run:

```bash
mkdir -p backups
docker compose stop app
docker run --rm \
  -v network-diagnostics-monitor_ndm-data:/data:ro \
  -v "$PWD/backups:/backup" \
  python:3.12-slim \
  sh -c 'test -f /data/network_diagnostics.db && cp /data/network_diagnostics.db /backup/network_diagnostics.db'
docker compose start app
```

Compose volume names can be prefixed by the project/directory name. Check `docker volume ls` and substitute the actual volume name if it differs. Keep backups outside version control and protect them if they contain operational information.

To restore, stop the app, copy the backup into the named volume using a temporary container with that volume mounted read-write, then start the app. Always verify the backup before overwriting the current database.

## Optional: Render demonstration

A Docker-based web service can be used for a temporary demonstration. Seeded metric history can be replayed with `network-diagnostics seed`, and HTML, Markdown, incident CSV, and per-device CSV reports can be written to protected storage:

1. If the API is deployed publicly, set a strong `NDM_API_KEY`; all acknowledge, resolve and diagnose POST requests then require the `X-API-Key` header. Add CSRF protection, authorization roles, TLS and a deployment-specific review before production use. Keep live API diagnosis disabled unless explicitly needed.
2. Free web-service filesystems are generally ephemeral. A SQLite file written inside a container can disappear when the service restarts or redeploys. Do not treat it as durable storage.
3. Persistent disks and always-on service features may incur charges. This project does not require Render or any paid infrastructure; local Docker is the reproducible, zero-subscription option.
4. If you later configure a persistent disk, mount it at `/var/data` and set `NDM_DATABASE_URL=sqlite:////var/data/network_diagnostics.db`. Confirm current platform pricing, filesystem semantics, and Python/Docker support in Render's official documentation before enabling a paid feature.
5. Bind the service to the platform-provided port as required by the platform. The supplied Docker image listens on port `8000`; configure the service to route to that port or adapt the startup command to the platform's `PORT` environment variable.

Do not configure `NDM_MODE=live` as a deployment shortcut. Live checks must remain opt-in and limited to authorized targets with explicit allowlisting. No deployment should expose this unauthenticated application to untrusted users.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NDM_MODE` | `simulated` | Default operating mode; leave simulated for demos. |
| `NDM_DATABASE_URL` | `sqlite:///./network_diagnostics.db` locally | SQLAlchemy database URL. Compose sets a persistent `/data` path. |
| `NDM_ALLOWED_TARGETS` | Sample allowlist in `.env.example` | Explicit targets permitted for live checks. |
| `NDM_ALLOW_LAB_RANGES` | `false` | Controls the documented lab-range exception; do not enable casually. |
| `NDM_TIMEOUT_SECONDS` | `3.0` | Live-check timeout setting. |
| `NDM_MIN_CHECK_INTERVAL_SECONDS` | `2.0` | Minimum interval between checks. |
| `NDM_DNS_RESOLVERS` | `1.1.1.1,8.8.8.8` | Configured DNS resolver list. |
| `NDM_ALLOW_LIVE_API` | `false` | Enables live `/api/diagnose` requests only when explicitly true. |
| `NDM_API_KEY` | unset | Optional shared key for all acknowledge, resolve and diagnose POST endpoints via `X-API-Key`. |

Do not commit API keys or database credentials. For public/shared deployments, set `NDM_API_KEY` to a strong secret and keep live API diagnosis disabled unless explicitly needed and allowlisted.

## Troubleshooting

- **Port 8000 is busy:** change the host side of the compose port mapping, for example `127.0.0.1:8001:8000`, then visit port 8001.
- **Dashboard is empty:** seed the database with `docker compose run --rm app network-diagnostics seed` and refresh.
- **Container is unhealthy:** inspect `docker compose logs app` and `docker compose ps`; check that port 8000 is reachable inside the container.
- **Database is read-only:** confirm the mounted volume is writable by the container's non-root UID and that `NDM_DATABASE_URL` points under `/data`.
- **Data disappeared:** confirm the named volume is still attached and that `docker compose down -v` was not run.
- **Dependency installation fails:** check Python/Docker version and package-index connectivity; do not work around this by removing declared dependency constraints.

## Production-readiness gaps

Before real public or organisational deployment, add role-based authorization, CSRF protection for browser state-changing actions, security headers, structured logging and retention policies, migrations, backup automation, monitoring of the monitoring service, dependency/image scanning, and a deployment-specific threat model. Consider PostgreSQL for multi-user or concurrent workloads. Keep network diagnostics opt-in and scoped to approved assets.
