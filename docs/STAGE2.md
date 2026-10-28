# Stage 2 — Monitoring and incident management

## Data model

- **Device** stores a fictional monitored asset's name, type, hostname, location and simulation flag.
- **Metric** stores a numeric observation, unit, status, timestamp, source and details. A compound index supports device/metric/time queries.
- **Incident** stores the incident kind, severity, lifecycle status, start/acknowledgement/resolution timestamps, duration, occurrence count and flapping flag.

SQLite is the default local persistence layer. Configure `NDM_DATABASE_URL` to override it. Schema creation is idempotent. Stage 2 uses SQLAlchemy metadata creation rather than migration tooling; migrations can be introduced when the schema needs to evolve.

## Simulation and safety

The seed inventory contains ten fictional devices. Metric data is generated locally using Python's seeded random generator plus deterministic scenario rules. It never sends network traffic and uses the `simulation` source marker. Default generation covers three days at hourly intervals. Re-running the same time range does not duplicate observations.

The simulator intentionally models:
- DNS latency/outage symptoms on the fictional DNS server.
- Elevated latency and packet loss on the edge router.
- HTTP 503 responses on the fictional web server.
- Intermittent availability on an access point.
- A synthetic TLS certificate nearing expiry.

TLS validity is a synthetic metric at this stage; it does not perform live certificate checks.

## Incident behavior

Default thresholds are declared in `incidents.DEFAULT_THRESHOLDS`. They can be overridden by passing a threshold mapping to `evaluate_incidents`. Open and acknowledged incidents are deduplicated by device and incident kind. Repeated abnormal latest readings increment `occurrence_count`; a healthy latest reading resolves the active incident and records its duration. The acknowledgement and resolution helpers validate incident IDs and lifecycle transitions.

Flapping is detected when recent availability samples cross between up and down at least four times within the latest twelve samples by default. This is a simple transparent rule suitable for a portfolio demonstration, not a replacement for production-grade alert correlation.

## CLI

```bash
network-diagnostics seed
network-diagnostics incidents
network-diagnostics incidents --status acknowledged
network-diagnostics acknowledge 2 --by "Technician"
network-diagnostics resolve 2
```

The CLI database defaults to `./network_diagnostics.db`; set `NDM_DATABASE_URL` to an alternate SQLAlchemy URL. Use `sqlite:///:memory:` in tests.

## Known limitations

- The schema is created with `create_all`; no Alembic migrations yet.
- The CLI seed command currently generates data and evaluates incidents in the same transaction.
- Incident evaluation examines each device's latest measurement per metric, so it is intended for batch/demo scenarios rather than continuous production ingestion.
- Thresholds are module defaults unless passed programmatically; external configuration and alert notification channels are out of scope.
