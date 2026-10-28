# Stage 3 — Troubleshooting recommendations and reports

## Recommendations

`recommendations.py` maps known incident types to ordered actions, rationale, and verification steps. Unknown incident kinds receive a generic evidence-gathering and escalation workflow. The recommendation engine is read-only: it does not mutate incidents or execute operational actions.

Guidance covers device unavailability, high latency, packet loss, DNS degradation, HTTP errors, TLS expiry, and availability flapping. TLS recommendations explicitly require verifying the actual certificate because Stage 2's TLS-days-remaining observations are synthetic.

## Reports

`reports.py` builds a report from persisted SQLAlchemy data and supports three renderers:

- **JSON** — structured summary, devices, incident lifecycle fields, and recommendation objects.
- **Markdown** — human-readable summary, incident table, and detailed recommended actions.
- **CSV** — one row per incident, with recommended actions flattened into a spreadsheet-friendly field.

The report summary includes device and metric counts, incident totals, active incident counts, severity/status breakdowns, and the oldest/newest metric timestamps. Empty databases are supported. Active incident duration is calculated at report-generation time.

## CLI

```bash
network-diagnostics recommendations
network-diagnostics recommendations 2
network-diagnostics report
network-diagnostics report --format json --output reports/monitoring-report.json
network-diagnostics report --format csv --output reports/incidents.csv
network-diagnostics report --format markdown --output reports/monitoring-report.md
```

The `NDM_DATABASE_URL` environment variable selects the database. Without `--output`, reports are written to stdout. With `--output`, parent directories are created and the rendered report is written as UTF-8.

## Safety and interpretation

Recommendations are advisory only and do not change device configuration, restart services, or run probes. Operators should validate symptoms, preserve evidence, and follow approved change-control and escalation processes. Report contents reflect the stored records; simulated measurements must not be interpreted as real-world observations.

## Known limitations

- Guidance is rule-based and intentionally transparent; it is not an automated root-cause engine.
- CSV exports contain one row per incident; a report with no incidents contains only the header row.
- Reports currently include all recorded incidents rather than filtering by a date range.
- The application has no scheduler or notification delivery in this stage.
