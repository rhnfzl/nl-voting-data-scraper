"""Tests for CLI commands."""

from click.testing import CliRunner

from nl_voting_data_scraper.cli import cli


class TestCLI:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "StemWijzer" in result.output

    def test_list_elections(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-elections"])
        assert result.exit_code == 0
        assert "gr2026" in result.output
        assert "municipal" in result.output

    def test_scrape_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scrape", "--help"])
        assert result.exit_code == 0
        assert "--municipality" in result.output
        assert "--output" in result.output
