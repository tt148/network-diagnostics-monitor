"""CLI tests use only the simulated backend."""

from typer.testing import CliRunner

from network_diagnostics_monitor.cli import app


def test_diagnose_defaults_to_simulated(monkeypatch, normalize_cli_output) -> None:
    monkeypatch.setenv("NDM_MODE", "simulated")
    runner = CliRunner()
    result = runner.invoke(app, ["diagnose", "example.com"])
    output = normalize_cli_output(result.output)
    assert result.exit_code == 0, output
    assert '"mode": "simulated"' in output
    assert "no HTTP request" in output
    assert '"findings"' in output
    assert '"layer": "application"' in output


def test_diagnose_rejects_unknown_mode(normalize_cli_output) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["diagnose", "example.com", "--mode", "bogus"])
    output = normalize_cli_output(result.output)
    assert result.exit_code != 0
    assert "mode must be" in output


def test_settings_accept_comma_separated_env(monkeypatch) -> None:
    from network_diagnostics_monitor.config import Settings

    monkeypatch.setenv("NDM_ALLOWED_TARGETS", "example.com, localhost")
    settings = Settings(_env_file=None)
    assert settings.allowed_targets == ["example.com", "localhost"]
