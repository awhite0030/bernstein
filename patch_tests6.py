import re

with open("tests/unit/cli/test_govern_audit_cmd.py", "r") as f:
    content = f.read()

# Add the explicit tests as requested by the plan.
new_tests = '''
from bernstein.core.govern.audit_sweep import CheckOutcome, CheckVerdict
from unittest.mock import patch

def test_govern_audit_exit_code_zero(project: Path) -> None:
    """Exit code 0 when every required check is measured/passed or declared."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, True, "sum1", ""),
            CheckOutcome("CMP-002", "area", CheckVerdict.DECLARED, None, "sum2", ""),
        )
        # Assuming CMP-001 is required
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001", "CMP-002"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project)])
            assert result.exit_code == 0

def test_govern_audit_exit_code_one_failed(project: Path) -> None:
    """Exit code 1 when any required check is measured and failed."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project)])
            assert result.exit_code == 1

def test_govern_audit_exit_code_two_strict(project: Path) -> None:
    """Exit code 2 when any required check is not_measurable and --strict is set."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.NOT_MEASURABLE, None, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--strict"])
            assert result.exit_code == 2

            # without strict, should be 0 (no failed, just not measurable)
            result_no_strict = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project)])
            assert result_no_strict.exit_code == 0

def test_govern_audit_quiet_mode(project: Path) -> None:
    """--quiet prints nothing."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--quiet"])
            assert result.exit_code == 1
            assert not result.output.strip()

def test_govern_audit_sarif_format(project: Path) -> None:
    """--format sarif emits SARIF 2.1.0."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", ""),
            CheckOutcome("CMP-002", "area", CheckVerdict.NOT_MEASURABLE, None, "sum2", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--format", "sarif"])
            assert result.exit_code == 1
            payload = json.loads(result.output)
            assert payload["version"] == "2.1.0"
            assert payload["runs"][0]["tool"]["driver"]["name"] == "bernstein"
            results = payload["runs"][0]["results"]
            assert len(results) == 2
            assert results[0]["ruleId"] == "CMP-001"
            assert results[0]["kind"] == "measured"
            assert results[0]["message"]["text"] == "sum1"

            assert results[1]["ruleId"] == "CMP-002"
            assert results[1]["kind"] == "not_measurable"
'''

content += new_tests

with open("tests/unit/cli/test_govern_audit_cmd.py", "w") as f:
    f.write(content)
