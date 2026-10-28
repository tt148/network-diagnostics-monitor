# Contributing (lite)

1. Use Python 3.12 and create a virtual environment.
2. Install development dependencies with `python -m pip install -e ".[dev]"`.
3. Keep tests deterministic; mock all live DNS/HTTP/ping interactions.
4. Run `ruff check .`, `ruff format --check .`, and `pytest --cov=network_diagnostics_monitor --cov-report=term-missing --cov-fail-under=85`.
5. Use conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`).
6. Never commit `.env`, credentials, or real user/network data.
