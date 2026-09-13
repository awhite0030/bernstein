"""CLI tests for ``bernstein govern audit-compliance`` over the compliance namespace (#5075)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from bernstein.cli.commands.governance_cmd import govern_group
from bernstein.core.govern.compliance_checks import iter_compliance_checks

if TYPE_CHECKING:
    from pathlib import Path

#: Words that would turn a report of what was read into an assertion of conformance.
_CONFORMANCE_CLAIMS = re.compile(r"\b(compliant|conformant|certified|certification|attests?)\b", re.IGNORECASE)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal install: a state directory and one configuration declaration."""
    (tmp_path / ".sdd").mkdir()
    (tmp_path / "bernstein.yaml").write_text("auth:\n  method: oidc\n", encoding="utf-8")
    return tmp_path


def _run(args: list[str], expected_exit: int | tuple[int, ...] = (0, 1, 2)) -> str:
    result = CliRunner().invoke(govern_group, args)
    if isinstance(expected_exit, int):
        assert result.exit_code == expected_exit, result.output
    else:
        assert result.exit_code in expected_exit, result.output
    return result.output


def test_govern_audit_list_names_every_registered_compliance_check(project: Path) -> None:
    """``--list`` prints the ids and areas the audit would run, without running them."""
    output = _run(["audit-compliance", "--workdir", str(project), "--list"])
    for spec in iter_compliance_checks():
        assert spec.check_id in output
        assert spec.area in output


def test_govern_audit_only_cmp_reports_every_registered_check(project: Path) -> None:
    """``--only CMP`` is the whole compliance namespace, one finding per registered check."""
    payload = json.loads(_run(["audit-compliance", "--workdir", str(project), "--only", "CMP", "--format", "json"]))
    reported = [row["check_id"] for row in payload["checks"]]
    assert reported == sorted(spec.check_id for spec in iter_compliance_checks())


def test_govern_audit_reports_counts_with_named_denominators_and_no_score(project: Path) -> None:
    """Every number is a fraction of a named denominator; there is no score and no grade."""
    payload = json.loads(_run(["audit-compliance", "--workdir", str(project), "--format", "json"]))
    counts = payload["counts"]
    assert set(counts) == {"measured_pass", "measured_fail", "declared", "not_measurable"}
    assert sum(counts.values()) == payload["checks_run"]
    assert "score" not in payload
    assert "grade" not in payload


def test_govern_audit_profile_marks_required_ids_and_emits_no_conformance_claim(project: Path) -> None:
    """A profile selects which ids are required and never claims the install conforms."""
    text = _run(["audit-compliance", "--workdir", str(project), "--profile", "soc2"])
    assert not _CONFORMANCE_CLAIMS.search(text), text

    payload = json.loads(_run(["audit-compliance", "--workdir", str(project), "--profile", "soc2", "--format", "json"]))
    assert payload["profile"] == "soc2"
    required = {row["check_id"] for row in payload["checks"] if row["required"]}
    assert required
    assert required < {row["check_id"] for row in payload["checks"]}
    assert "conformance" not in json.dumps(payload).lower()


def test_govern_audit_skip_removes_only_the_named_id(project: Path) -> None:
    """Skipping is a filter on what runs, not a suppression of what was found."""
    target = iter_compliance_checks()[0].check_id
    payload = json.loads(_run(["audit-compliance", "--workdir", str(project), "--skip", target, "--format", "json"]))
    reported = {row["check_id"] for row in payload["checks"]}
    assert target not in reported
    assert len(reported) == len(iter_compliance_checks()) - 1


def test_govern_audit_rejects_an_unknown_selector(project: Path) -> None:
    """A selector that matches no registered id fails loudly instead of auditing nothing."""
    result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--only", "XYZ"])
    assert result.exit_code != 0
    assert "XYZ" in result.output

from unittest.mock import patch

from bernstein.core.govern.audit_sweep import CheckOutcome, CheckVerdict


def test_govern_audit_exit_code_zero(project: Path) -> None:
    """Exit code 0 when every required check is measured/passed or declared."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, True, "sum1", ""),
            CheckOutcome("CMP-002", "area", CheckVerdict.DECLARED, None, "sum2", ""),
        )
        # Assuming CMP-001 is required
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001", "CMP-002"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2"])
            assert result.exit_code == 0

def test_govern_audit_exit_code_one_failed(project: Path) -> None:
    """Exit code 1 when any required check is measured and failed."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2"])
            assert result.exit_code == 1

def test_govern_audit_exit_code_two_strict(project: Path) -> None:
    """Exit code 2 when any required check is not_measurable and --strict is set."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.NOT_MEASURABLE, None, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2", "--strict"])
            assert result.exit_code == 2

            # without strict, should be 0 (no failed, just not measurable)
            result_no_strict = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2"])
            assert result_no_strict.exit_code == 0

def test_govern_audit_quiet_mode(project: Path) -> None:
    """--quiet prints nothing."""
    with patch("bernstein.cli.commands.governance_cmd.run_compliance_checks") as mock_run:
        mock_run.return_value = (
            CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", ""),
        )
        with patch("bernstein.cli.commands.governance_cmd.required_check_ids", return_value={"CMP-001"}):
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2", "--quiet"])
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
            result = CliRunner().invoke(govern_group, ["audit-compliance", "--workdir", str(project), "--profile", "soc2", "--format", "sarif"])
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
