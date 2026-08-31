from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from bernstein.cli.main import cli


def test_adapters_onboard_cmd_basic(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["adapters", "onboard", "python", "--out-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Probing binary: python" in result.output
    assert "Wrote 5 evidence files to" in result.output

    # Check that 5 json files are generated in the target directory.
    evidence_files = list(tmp_path.glob("*.json"))
    assert len(evidence_files) == 5

def test_adapters_onboard_group_registration() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["adapters", "--help"])
    assert result.exit_code == 0
    assert "onboard" in result.output
