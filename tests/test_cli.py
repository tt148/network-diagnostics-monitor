"""CLI tests use only the simulated backend."""

from typer.testing import CliRunner

from network_diagnostics_monitor.cli import app


def test_diagnose_defaults_to_simulated(monkeypatch) -> None:
    monkeypatch.setenv("NDM_MODE", "simulated")
    runner = CliRunner()
    result = runner.invoke(app, ["diagnose", "example.com"])
    assert result.exit_code == 0, result.output
    assert '"mode": "simulated"' in result.output
    assert "no HTTP request" in result.output
    assert '"findings"' in result.output
    assert '"layer": "application"' in result.output


def test_diagnose_rejects_unknown_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["diagnose", "example.com", "--mode", "bogus"])
    assert result.exit_code != 0


def test_settings_accept_comma_separated_env(monkeypatch) -> None:
    from network_diagnostics_monitor.config import Settings

    monkeypatch.setenv("NDM_ALLOWED_TARGETS", "example.com, localhost")
    settings = Settings(_env_file=None)
    assert settings.allowed_targets == ["example.com", "localhost"]
