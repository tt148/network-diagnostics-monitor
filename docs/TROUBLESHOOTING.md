# Troubleshooting patterns

This page will expand in later stages. Stage 1 provides the diagnostic primitives.

- **Name fails, IP works:** suspect DNS. Compare resolver answers and inspect configured DNS servers.
- **No latency samples:** check local link and gateway first, then routing/firewall policy. TCP fallback tests only a single connection to port 443; it is not a port scan.
- **HTTP 5xx:** network reachability may be healthy while the application or upstream dependency is failing.
- **TLS validation failure:** check hostname/SAN match, trust chain, system clock, and certificate expiry.
- **Private IP rejected:** this is an intentional safety control. Only enable `NDM_ALLOW_LAB_RANGES=true` for a controlled lab and only after understanding the risk.
- **Target rejected:** live mode only accepts a hostname/IP explicitly listed in `NDM_ALLOWED_TARGETS`.
