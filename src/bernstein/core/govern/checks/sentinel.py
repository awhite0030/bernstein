from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bernstein.core.checks.contract import Evidence, Finding, Verdict

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class SentinelCheck:
    """A check that fails if the sentinel environment variable is set.

    Issue #5091. Proves the detect -> record -> notify path end to end without
    breaking anything real. If BERNSTEIN_GOVERN_AUDIT_SENTINEL is set, it reports
    a measured failure with a fixed reason. Otherwise, it passes.
    """

    check_id: str = "GOV:SENTINEL-1"
    title: str = "Sentinel Failure Injector"
    description: str = "Fails if BERNSTEIN_GOVERN_AUDIT_SENTINEL is set."

    def run(self, workdir: Path | None = None) -> Finding:
        dummy_evidence = Evidence.from_bytes("sentinel-env", b"dummy")
        if "BERNSTEIN_GOVERN_AUDIT_SENTINEL" in os.environ:
            return Finding(
                check_id=self.check_id,
                verdict=Verdict.MEASURED,
                passed=False,
                summary="sentinel_injected_failure",
                reason="Sentinel environment variable BERNSTEIN_GOVERN_AUDIT_SENTINEL is set",
                evidence=(dummy_evidence,),
            )
        return Finding(
            check_id=self.check_id,
            verdict=Verdict.MEASURED,
            passed=True,
            summary="sentinel_not_injected",
            evidence=(dummy_evidence,),
        )

    def __call__(self, workdir: Path | None = None) -> Finding:
        return self.run(workdir)
