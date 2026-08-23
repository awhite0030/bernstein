"""Tests for per-part content-hash context receipts.

Exercises :mod:`bernstein.core.agents.context_receipt` - data structures,
the builder, and the save/load round-trip - directly against the real
implementation. No mocks of the unit under test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bernstein.core.agents.context_receipt import (
    ContextReceipt,
    ReceiptEntry,
    build_context_receipt,
    load_context_receipt,
    save_context_receipt,
)

# ---------------------------------------------------------------------------
# build_context_receipt
# ---------------------------------------------------------------------------


class TestBuildContextReceipt:
    def test_builds_entry_per_non_empty_section(self) -> None:
        sections = [("role", "You are an agent."), ("task", "Do the thing.")]
        receipt = build_context_receipt(sections, session_id="s1")

        assert receipt.session_id == "s1"
        assert receipt.section_count == 2
        assert len(receipt.entries) == 2
        assert receipt.entries[0].label == "role"
        assert receipt.entries[1].label == "task"

    def test_skips_blank_sections(self) -> None:
        sections = [("role", "content"), ("empty", ""), ("spaces", "   "), ("task", "more")]
        receipt = build_context_receipt(sections)

        assert receipt.section_count == 2
        assert [e.label for e in receipt.entries] == ["role", "task"]

    def test_computes_sha256(self) -> None:
        content = "hello world"
        sections = [("x", content)]
        receipt = build_context_receipt(sections)

        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert receipt.entries[0].content_sha256 == expected

    def test_char_count_is_len_content(self) -> None:
        content = "abcd"
        receipt = build_context_receipt([("x", content)])
        assert receipt.entries[0].char_count == 4

    def test_token_estimate_is_positive(self) -> None:
        receipt = build_context_receipt([("x", "a substantial piece of text")])
        assert receipt.entries[0].token_estimate > 0

    def test_totals_are_summed(self) -> None:
        sections = [("a", "first section"), ("b", "second section here")]
        receipt = build_context_receipt(sections)

        assert receipt.total_tokens == sum(e.token_estimate for e in receipt.entries)
        assert receipt.total_chars == sum(e.char_count for e in receipt.entries)

    def test_empty_sections_list(self) -> None:
        receipt = build_context_receipt([])
        assert receipt.section_count == 0
        assert receipt.entries == []
        assert receipt.total_tokens == 0
        assert receipt.total_chars == 0

    def test_all_blank_sections(self) -> None:
        receipt = build_context_receipt([("a", ""), ("b", "  ")])
        assert receipt.section_count == 0
        assert receipt.entries == []

    def test_default_session_id(self) -> None:
        receipt = build_context_receipt([("x", "content")])
        assert receipt.session_id == ""


# ---------------------------------------------------------------------------
# ReceiptEntry round-trip
# ---------------------------------------------------------------------------


class TestReceiptEntrySerialization:
    def test_to_dict_round_trip(self) -> None:
        entry = ReceiptEntry(
            label="role",
            content_sha256="abc123",
            token_estimate=10,
            char_count=20,
        )
        d = entry.to_dict()
        assert d == {
            "label": "role",
            "content_sha256": "abc123",
            "token_estimate": 10,
            "char_count": 20,
        }
        restored = ReceiptEntry.from_dict(d)
        assert restored == entry


# ---------------------------------------------------------------------------
# ContextReceipt round-trip
# ---------------------------------------------------------------------------


class TestContextReceiptSerialization:
    def test_to_dict_round_trip(self) -> None:
        entries = [
            ReceiptEntry(label="a", content_sha256="hash1", token_estimate=5, char_count=10),
            ReceiptEntry(label="b", content_sha256="hash2", token_estimate=8, char_count=16),
        ]
        receipt = ContextReceipt(
            session_id="test-session",
            entries=entries,
            total_tokens=13,
            total_chars=26,
            section_count=2,
        )
        d = receipt.to_dict()
        assert d["session_id"] == "test-session"
        assert d["section_count"] == 2
        assert d["total_tokens"] == 13
        assert d["total_chars"] == 26
        assert len(d["entries"]) == 2

        restored = ContextReceipt.from_dict(d)
        assert restored.session_id == "test-session"
        assert restored.section_count == 2
        assert restored.total_tokens == 13
        assert restored.total_chars == 26
        assert restored.entries == entries

    def test_from_dict_missing_fields_defaults(self) -> None:
        restored = ContextReceipt.from_dict({})
        assert restored.session_id == ""
        assert restored.entries == []
        assert restored.total_tokens == 0


# ---------------------------------------------------------------------------
# save / load persistence
# ---------------------------------------------------------------------------


class TestSaveLoad:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        receipt = build_context_receipt(
            [("role", "You are an agent."), ("task", "Do the thing.")],
            session_id="abc123",
        )
        out_path = save_context_receipt(receipt, tmp_path)
        assert out_path.exists()
        assert "context_receipt_abc123.json" in out_path.name

        loaded = load_context_receipt(tmp_path / ".sdd", "abc123")
        assert loaded is not None
        assert loaded.session_id == receipt.session_id
        assert loaded.section_count == receipt.section_count
        assert loaded.entries == receipt.entries

    def test_save_creates_metrics_dir(self, tmp_path: Path) -> None:
        receipt = build_context_receipt([("x", "content")], session_id="s1")
        metrics_dir = tmp_path / ".sdd" / "metrics"
        assert not metrics_dir.exists()

        out_path = save_context_receipt(receipt, tmp_path)
        assert metrics_dir.exists()
        assert out_path.parent == metrics_dir

    def test_load_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = load_context_receipt(tmp_path / ".sdd", "nonexistent")
        assert result is None

    def test_load_returns_none_for_corrupt_json(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".sdd" / "metrics"
        metrics_dir.mkdir(parents=True)
        bad_file = metrics_dir / "context_receipt_corrupt.json"
        bad_file.write_text("{not valid json", encoding="utf-8")

        result = load_context_receipt(tmp_path / ".sdd", "corrupt")
        assert result is None

    def test_load_returns_none_for_non_dict_json(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".sdd" / "metrics"
        metrics_dir.mkdir(parents=True)
        bad_file = metrics_dir / "context_receipt_bad.json"
        bad_file.write_text("[1, 2, 3]", encoding="utf-8")

        result = load_context_receipt(tmp_path / ".sdd", "bad")
        assert result is None

    def test_save_without_session_id(self, tmp_path: Path) -> None:
        receipt = build_context_receipt([("x", "content")])
        out_path = save_context_receipt(receipt, tmp_path)
        assert out_path.name == "context_receipt.json"

    def test_saved_file_is_valid_json(self, tmp_path: Path) -> None:
        receipt = build_context_receipt(
            [("role", "You are an agent.")],
            session_id="json-test",
        )
        out_path = save_context_receipt(receipt, tmp_path)
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["session_id"] == "json-test"
        assert "entries" in data
