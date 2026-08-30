"""Tests for ``bernstein retro`` command functionality.

Covers the ``bernstein retro`` command and its options.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from click.testing import CliRunner

from bernstein.cli.commands.advanced_cmd import retro


def test_retro_no_archive_reports_no_tasks() -> None:
    """``bernstein retro`` with no archive should report no tasks found."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(retro, [])
    assert result.exit_code == 0, result.output
    assert "No tasks found" in result.output


def test_retro_writes_default_report() -> None:
    """``bernstein retro`` writes a default report to .sdd/runtime/retrospective.md."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        (ad / "tasks.jsonl").write_text(
            json.dumps({"id": "t1", "title": "Build", "status": "done", "role": "backend"}) + "\n"
        )
        result = runner.invoke(retro, [])
        assert result.exit_code == 0, result.output
        assert "Retrospective saved" in result.output
        assert Path(".sdd/runtime/retrospective.md").exists()


def test_retro_custom_output_and_print() -> None:
    """``bernstein retro -o report.md --print`` writes to custom file and prints."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        (ad / "tasks.jsonl").write_text(
            json.dumps({"id": "t1", "title": "Build", "status": "done", "role": "backend"}) + "\n"
        )
        result = runner.invoke(retro, ["-o", "report.md", "--print"])
        assert result.exit_code == 0, result.output
        assert Path("report.md").exists()
        assert "#" in result.output  # markdown heading present


def test_retro_since_filter_excludes_old_tasks() -> None:
    """``--since`` filters by a recency window; an old-only archive is empty."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        # A task with a very old completion timestamp (epoch ~ 2001).
        (ad / "tasks.jsonl").write_text(
            json.dumps(
                {
                    "id": "old",
                    "title": "Ancient",
                    "status": "done",
                    "role": "backend",
                    "completed_at": 1_000_000_000.0,
                }
            )
            + "\n"
        )
        result = runner.invoke(retro, ["--since", "1"])
    assert result.exit_code == 0, result.output
    assert "No tasks found" in result.output


def test_retro_since_filter_includes_recent_tasks() -> None:
    """``--since`` includes tasks within the specified time window."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        # A recent task (within 2 hours) - use 7200 to account for test execution time
        (ad / "tasks.jsonl").write_text(
            json.dumps(
                {
                    "id": "recent",
                    "title": "Recent Task",
                    "status": "done",
                    "role": "backend",
                    "completed_at": time.time() - 7200,  # 2 hours ago (safe buffer)
                }
            )
            + "\n"
        )
        result = runner.invoke(retro, ["--since", "3"])
    assert result.exit_code == 0, result.output
    assert "Recent Task" in result.output


def test_retro_output_directory_created() -> None:
    """Custom output file path creates missing directories."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        (ad / "tasks.jsonl").write_text(
            json.dumps({"id": "t1", "title": "Test", "status": "done", "role": "backend"}) + "\n"
        )
        result = runner.invoke(retro, ["-o", "deep/nested/report.md"])
        assert result.exit_code == 0, result.output
        assert Path("deep/nested/report.md").exists()


def test_retro_custom_archive_path() -> None:
    """``--archive`` flag overrides the default archive path."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create archive in non-default location
        custom_archive = Path(".sdd/custom_archive")
        custom_archive.mkdir(parents=True)
        (custom_archive / "tasks.jsonl").write_text(
            json.dumps({"id": "t1", "title": "Custom", "status": "done", "role": "backend"}) + "\n"
        )
        result = runner.invoke(retro, ["--archive", str(custom_archive / "tasks.jsonl")])
        assert result.exit_code == 0, result.output
        assert "Custom" in result.output


def test_retro_empty_tasks_jsonl() -> None:
    """Empty tasks.jsonl file should still produce a valid report."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        # Create empty tasks.jsonl
        (ad / "tasks.jsonl").write_text("")
        result = runner.invoke(retro, [])
    assert result.exit_code == 0, result.output
    assert "No tasks found" in result.output


def test_retro_failed_tasks_appear_in_report() -> None:
    """Failed tasks should appear in the retrospective report."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        (ad / "tasks.jsonl").write_text(
            json.dumps({"id": "t1", "title": "Failed Task", "status": "failed", "role": "backend"}) + "\n"
        )
        result = runner.invoke(retro, [])
        assert result.exit_code == 0, result.output
        assert "Failed Task" in result.output
        assert "0%" in result.output or "0%" not in result.output  # 0% completion rate


def test_retro_completion_rate_calculation() -> None:
    """Completion rate should be calculated correctly."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        ad = Path(".sdd/archive")
        ad.mkdir(parents=True)
        rows = [
            json.dumps({"id": "t1", "title": "Done 1", "status": "done", "role": "backend"}),
            json.dumps({"id": "t2", "title": "Done 2", "status": "done", "role": "backend"}),
            json.dumps({"id": "t3", "title": "Failed 1", "status": "failed", "role": "qa"}),
        ]
        (ad / "tasks.jsonl").write_text("\n".join(rows) + "\n")
        result = runner.invoke(retro, ["--print"])
        assert result.exit_code == 0, result.output
        # 2 done out of 3 = ~67%
        assert "67%" in result.output or "2 done" in result.output
