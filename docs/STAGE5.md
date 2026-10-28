# Stage 5 — Packaging, documentation, and deployment

## Delivered

- `Dockerfile`: Python 3.12 slim image, runtime-only install, non-root account, simulated default, SQLite data path, and HTTP health check.
- `compose.yaml`: local-only port publishing, persistent named volume, read-only root filesystem, `no-new-privileges`, temporary filesystem, restart policy, and health check.
- `.dockerignore`: excludes Git data, environments, caches, local databases, tests, and generated reports from the image build context.
- `docs/DEPLOYMENT.md`: local and Docker runbooks, database persistence and backup notes, environment variables, troubleshooting, and a cautious optional Render section.
- `docs/images/architecture.svg`: hand-authored architecture diagram showing user interfaces, domain services, storage, and deployment boundaries.
- `README.md`: final architecture, Docker quick start, docs links, and project limitations.

## Local Docker workflow

```bash
docker compose build
docker compose up -d
docker compose run --rm app network-diagnostics seed
docker compose ps
docker compose logs app
```

The dashboard is available at `http://127.0.0.1:8000/`. Keep it local: authentication and authorization are not implemented yet.

## Architecture diagram

The editable source is `docs/images/architecture.svg`. It is plain SVG markup and can be reviewed or edited in a text editor or vector graphics application.

## Verification checklist

- Run Ruff lint and formatting checks.
- Run the full pytest suite with the configured 85% coverage gate.
- Build and start the container using Docker Compose.
- Confirm `/api/health` responds and the container reports healthy.
- Seed simulated data, restart the container, and confirm the data persists.
- Confirm the published host port is bound to `127.0.0.1`, not all interfaces.
- Do not deploy publicly until authentication/authorization and CSRF protections are implemented.

Docker was not available in the implementation environment at the time this stage was prepared, so the container build and Compose runtime checks must be performed on a machine with Docker installed.
