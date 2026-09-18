"""Test the govern audit sentinel (Issue #5091).

A sentinel environment variable forces a known, named check to fail. This is the
mechanism that proves the detect-record-notify path end-to-end without breaking
anything real.

We use an environment variable (BERNSTEIN_GOVERN_AUDIT_SENTINEL) because it is
easier to avoid the "forgotten sentinel" risk than a file (which persists across
process boundaries and could accidentally silence real checks in a later test).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from bernstein.core.checks.contract import Finding, Verdict
from bernstein.core.govern.checks.sentinel import SentinelCheck
from bernstein.core.lineage.spine import LineageSpine
from bernstein.core.security.audit import load_or_create_audit_key


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass
class AuditRunResult:
    finding: Finding
    run_output: str
    journal_entry_hash: str | None


def _run_sentinel_audit(workdir: Path) -> AuditRunResult:
    """Stub of the detect -> record -> notify chain."""
    check = SentinelCheck()
    finding = check.run(workdir)

    output: list[str] = []
    journal_entry_hash: str | None = None

    if finding.passed is False:
        output.append(f"Check {finding.check_id} failed: {finding.summary}")
        if "BERNSTEIN_GOVERN_AUDIT_SENTINEL" in os.environ:
            output.append("SENTINEL ACTIVE: BERNSTEIN_GOVERN_AUDIT_SENTINEL is set.")

        lineage_root = workdir / ".sdd" / "lineage"
        lineage_root.mkdir(parents=True, exist_ok=True)
        hmac_key = load_or_create_audit_key()
        spine = LineageSpine(lineage_root, run_id="govern-audit", hmac_key=hmac_key)

        timestamp = int(time.time())
        content_payload: dict[str, Any] = {
            "check_id": finding.check_id,
            "verdict": finding.verdict.value,
            "passed": finding.passed,
            "summary": finding.summary,
        }

        journal_entry_hash = spine.record(
            artifact_path="govern-audit/finding.json",
            content=_canonical_bytes(content_payload),
            actor="bernstein.govern.audit",
            step_id=finding.check_id,
            model="none",
            timestamp=timestamp,
        )

        output.append(f"Recorded finding: {journal_entry_hash}")
        output.append(f"Notified failure: {finding.check_id}")
    else:
        output.append(f"Check {finding.check_id} passed.")

    return AuditRunResult(
        finding=finding,
        run_output="\n".join(output),
        journal_entry_hash=journal_entry_hash,
    )


def test_sentinel_forces_named_check_to_measured_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BERNSTEIN_GOVERN_AUDIT_SENTINEL", "1")
    check = SentinelCheck()
    finding = check.run(tmp_path)
    assert finding.verdict == Verdict.MEASURED
    assert finding.passed is False
    assert finding.summary == "sentinel_injected_failure"
    assert finding.check_id == "GOV:SENTINEL-1"


def test_sentinel_presence_is_reported_in_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BERNSTEIN_GOVERN_AUDIT_SENTINEL", "1")
    result = _run_sentinel_audit(tmp_path)
    assert "SENTINEL ACTIVE: BERNSTEIN_GOVERN_AUDIT_SENTINEL is set." in result.run_output


def test_full_chain_detect_record_notify_fires_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Set the sentinel
    monkeypatch.setenv("BERNSTEIN_GOVERN_AUDIT_SENTINEL", "1")

    # 2. Run the audit
    result = _run_sentinel_audit(tmp_path)

    # 3. Assert the finding (detect)
    assert result.finding.passed is False

    # 4. Assert the journal entry (record)
    assert result.journal_entry_hash is not None
    assert result.journal_entry_hash.startswith("sha256:")
    assert f"Recorded finding: {result.journal_entry_hash}" in result.run_output

    # 5. Assert the notification (notify)
    assert f"Notified failure: {result.finding.check_id}" in result.run_output

    # 6. Clear the sentinel and confirm it's gone
    monkeypatch.delenv("BERNSTEIN_GOVERN_AUDIT_SENTINEL")
    result_clean = _run_sentinel_audit(tmp_path)
    assert result_clean.finding.passed is True
    assert result_clean.journal_entry_hash is None
