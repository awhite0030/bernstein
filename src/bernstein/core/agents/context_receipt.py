"""Per-part content-hash context receipts.

After a prompt is assembled from named sections in :mod:`spawn_prompt`, this
module records a content-hash receipt for each section that was actually
included.  Each entry captures the section label, a SHA-256 hash of its
content, an estimated token count, and its raw character count.  The receipt
as a whole aggregates per-section totals so callers can verify that the
context handed to an agent matches what was intended (e.g. for prompt-cache
locality or audit purposes).

The receipt is persisted to ``.sdd/metrics/context_receipt_{session_id}.json``,
mirroring the ``save_prompt_token_report`` pattern in
:mod:`bernstein.core.tokens.prompt_token_analysis`.

Usage::

    from bernstein.core.agents.context_receipt import build_context_receipt

    receipt = build_context_receipt(named_sections, session_id="abc")
    save_context_receipt(receipt, workdir)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bernstein.core.tokens.token_estimation import estimate_tokens_for_text

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ReceiptEntry:
    """Content-hash receipt for a single named prompt section.

    Attributes:
        label: Section label (e.g. ``"role"``, ``"lessons"``).
        content_sha256: SHA-256 hex digest of the section content.
        token_estimate: Estimated token count for the section.
        char_count: Raw character count of the section content.
    """

    label: str
    content_sha256: str
    token_estimate: int
    char_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        return {
            "label": self.label,
            "content_sha256": self.content_sha256,
            "token_estimate": self.token_estimate,
            "char_count": self.char_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReceiptEntry:
        """Reconstruct a :class:`ReceiptEntry` from a serialised dict.

        Args:
            data: Dict as produced by :meth:`to_dict`.

        Returns:
            A new :class:`ReceiptEntry`.
        """
        return cls(
            label=str(data.get("label", "")),
            content_sha256=str(data.get("content_sha256", "")),
            token_estimate=int(data.get("token_estimate", 0)),
            char_count=int(data.get("char_count", 0)),
        )


@dataclass
class ContextReceipt:
    """Aggregate content-hash receipt for a full prompt.

    Attributes:
        session_id: Agent session this receipt belongs to (empty if N/A).
        entries: Per-section receipts, in the order they were included.
        total_tokens: Sum of all entry token estimates.
        total_chars: Sum of all entry character counts.
        section_count: Number of entries in the receipt.
    """

    session_id: str
    entries: list[ReceiptEntry] = field(default_factory=list[ReceiptEntry])
    total_tokens: int = 0
    total_chars: int = 0
    section_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        return {
            "session_id": self.session_id,
            "total_tokens": self.total_tokens,
            "total_chars": self.total_chars,
            "section_count": self.section_count,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextReceipt:
        """Reconstruct a :class:`ContextReceipt` from a serialised dict.

        Args:
            data: Dict as produced by :meth:`to_dict`.

        Returns:
            A new :class:`ContextReceipt`.
        """
        raw_entries = data.get("entries", [])
        entries = [
            ReceiptEntry.from_dict(e) if isinstance(e, dict) else ReceiptEntry.from_dict({})
            for e in raw_entries
        ]
        return cls(
            session_id=str(data.get("session_id", "")),
            entries=entries,
            total_tokens=int(data.get("total_tokens", 0)),
            total_chars=int(data.get("total_chars", 0)),
            section_count=int(data.get("section_count", 0)),
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_context_receipt(
    named_sections: list[tuple[str, str]],
    session_id: str = "",
) -> ContextReceipt:
    """Build a content-hash receipt for a prompt's named sections.

    Args:
        named_sections: List of ``(label, content)`` pairs as produced by
            :func:`bernstein.core.spawn_prompt._render_prompt`.
        session_id: Agent session identifier (used for labelling only).

    Returns:
        :class:`ContextReceipt` with one entry per non-blank section.
    """
    entries: list[ReceiptEntry] = []
    for label, content in named_sections:
        if not content.strip():
            # Skip empty/blank sections - only record what was actually included.
            continue
        entries.append(
            ReceiptEntry(
                label=label,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                token_estimate=estimate_tokens_for_text(content, assumed_type="text"),
                char_count=len(content),
            )
        )

    return ContextReceipt(
        session_id=session_id,
        entries=entries,
        total_tokens=sum(e.token_estimate for e in entries),
        total_chars=sum(e.char_count for e in entries),
        section_count=len(entries),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_context_receipt(receipt: ContextReceipt, workdir: Path) -> Path:
    """Write a context receipt to ``.sdd/metrics/``.

    Args:
        receipt: The receipt to persist.
        workdir: Project root directory.

    Returns:
        Path to the written file.
    """
    metrics_dir = workdir / ".sdd" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    name = f"context_receipt_{receipt.session_id}.json" if receipt.session_id else "context_receipt.json"
    out_path = metrics_dir / name
    try:
        out_path.write_text(json.dumps(receipt.to_dict(), indent=2), encoding="utf-8")
        # "token" here is an LLM context-token usage report, not a credential.
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        logger.debug("Context receipt written: %s", out_path)
    except OSError as exc:
        # "token" here is an LLM context-token usage report, not a credential.
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        logger.warning("Failed to write context receipt: %s", exc)
    return out_path


def load_context_receipt(sdd_dir: Path, session_id: str) -> ContextReceipt | None:
    """Load a saved context receipt for a session.

    Args:
        sdd_dir: Project root ``.sdd/`` directory.
        session_id: Agent session identifier.

    Returns:
        :class:`ContextReceipt`, or None if no receipt exists or it cannot
        be parsed.
    """
    metrics_dir = sdd_dir / "metrics"
    report_path = metrics_dir / f"context_receipt_{session_id}.json"
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Strip CR/LF from the user-controlled session_id before logging
        # so an attacker cannot inject fake log lines (CodeQL
        # py/log-injection #98).
        safe_sid = session_id.replace("\r", "").replace("\n", "")
        # "token" here is an LLM context-token usage report, not a credential.
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        logger.debug("Cannot load context receipt for %s: %s", safe_sid, exc)
        return None
    if not isinstance(data, dict):
        return None
    return ContextReceipt.from_dict(data)
