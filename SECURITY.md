# Security policy

This is a portfolio project, not a security scanner. Simulated mode is the default. Live probes require explicit allowlisting, use hard timeouts and a process-local rate limiter, and reject private/special-use IPs unless lab ranges are explicitly enabled. HTML reports escape persisted values and contain no external assets; CSV exports guard spreadsheet formula-leading cells. Set `NDM_API_KEY` for public or shared deployments: acknowledge, resolve and diagnose POST endpoints require the matching `X-API-Key` header, compared in constant time. Live API diagnosis remains disabled unless `NDM_ALLOW_LIVE_API=true`; public deployments also require TLS, authorization/CSRF review and network monitoring controls.

Please report suspected vulnerabilities privately to the repository maintainer rather than posting sensitive details publicly. Do not test systems you do not own or have permission to assess.
