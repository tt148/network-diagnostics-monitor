# Security policy

This is a portfolio project, not a security scanner. Simulated mode is the default. Live probes require explicit allowlisting, use hard timeouts and a process-local rate limiter, and reject private/special-use IPs unless lab ranges are explicitly enabled. HTML reports escape persisted values and contain no external assets; CSV exports guard spreadsheet formula-leading cells. Any public deployment still requires authentication and authorization that is added in a later phase; the current API remains unauthenticated.

Please report suspected vulnerabilities privately to the repository maintainer rather than posting sensitive details publicly. Do not test systems you do not own or have permission to assess.
