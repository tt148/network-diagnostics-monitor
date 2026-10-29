# Troubleshooting patterns

A layered method works best: local link, then gateway, then IP reachability, then DNS, then the application. The checks in this project follow the same order.

| Symptom | Likely layer | What to check |
|---|---|---|
| Name fails, IP works | DNS | Compare answers from two resolvers, inspect the configured DNS servers, try a known-good name. |
| No latency samples | Link, gateway or firewall | Check the local link and default gateway first, then routing and firewall policy. The TCP fallback makes a single connection to port 443; it is not a port scan. |
| Ping loss but TCP connects | ICMP filtering or congestion | Compare loss over several low-rate samples before blaming the path. |
| High jitter | Congestion or wireless | Review interface utilization, errors and queue drops on the affected path. |
| HTTP 5xx | Application or upstream | Reachability can be healthy while the application or a dependency fails; check logs and recent deployments. |
| TLS validation failure | Certificate | Check hostname/SAN match, trust chain, system clock and expiry date. |
| Redirect reported as `degraded` | Expectation | The HTTP check does not follow redirects; set the expected status to the redirect code or use the final URL. |
| Private IP rejected | Safety control | Intentional. Only set `NDM_ALLOW_LAB_RANGES=true` in a controlled lab and after understanding the risk. |
| Target rejected | Safety control | Live mode only accepts targets listed in `NDM_ALLOWED_TARGETS`. |

## Running the project

- **`ping` is not installed, or ICMP is not permitted (containers, some CI runners):** the latency check automatically falls back to TCP connect timing and reports `method: tcp-connect-fallback`.
- **`ruff format --check` fails in CI:** run `ruff format .` locally and commit the result.
- **Dashboard is empty:** run `network-diagnostics seed` against the same `NDM_DATABASE_URL` the server uses.
