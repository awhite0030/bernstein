import json
import hashlib
import os
from pathlib import Path

import pytest

# Import the adapter module
from src.bernstein.adapters.holmesgpt import (
    parse_output,
    verify_evidence,
    build_filtered_env,
)


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


def test_happy_path_structured_output(temp_dir):
    # Create data source files
    data_dir = temp_dir / "data"
    data_dir.mkdir()
    source1_path = data_dir / "source1.txt"
    source1_content = b"some data"
    source1_path.write_bytes(source1_content)
    hash1 = hashlib.sha256(source1_content).hexdigest()

    source2_path = data_dir / "source2.json"
    source2_content = b'{"key": "value"}'
    source2_path.write_bytes(source2_content)
    hash2 = hashlib.sha256(source2_content).hexdigest()

    # Create structured output file
    output_content = {
        "conclusion": "All good",
        "terminal_state": "OK",
        "data_sources": [
            {"path": str(source1_path), "hash": hash1},
            {"path": str(source2_path), "hash": hash2},
        ],
    }
    output_path = temp_dir / "output.json"
    output_path.write_text(json.dumps(output_content))

    # Call the parser
    result = parse_output(str(output_path))

    # Assertions
    assert result["conclusion"] == "All good"
    assert result["terminal_state"] == "OK"
    assert result["data_sources"][0]["path"] == str(source1_path)
    assert result["data_sources"][0]["hash"] == hash1
    assert result["data_sources"][1]["path"] == str(source2_path)
    assert result["data_sources"][1]["hash"] == hash2


def test_malformed_output_refusal(temp_dir):
    # Create a file with malformed JSON (missing closing brace)
    output_path = temp_dir / "malformed.json"
    output_path.write_text('{"key": "value"')  # missing closing brace

    # Call the parser; expect a ValueError or similar
    with pytest.raises(ValueError):
        parse_output(str(output_path))


def test_inconclusive_run_receipt(temp_dir):
    # Create output without conclusion
    output_content = {
        "terminal_state": "OK",
        # no "conclusion" field
    }
    output_path = temp_dir / "inconclusive.json"
    output_path.write_text(json.dumps(output_content))

    result = parse_output(str(output_path))

    # Assert that result indicates no conclusion
    assert "reason_code" in result
    assert result["reason_code"] == "NO_CONCLUSION"


def test_unreachable_data_source_receipt(temp_dir):
    # Create output that references a data source file that does not exist
    output_content = {
        "conclusion": "Missing file",
        "data_sources": [
            {"path": str(temp_dir / "missing.txt"), "hash": "dummy_hash"},
        ],
        "terminal_state": "OK",
    }
    output_path = temp_dir / "unreachable.json"
    output_path.write_text(json.dumps(output_content))

    result = parse_output(str(output_path))

    assert result["reason_code"] == "DATA_SOURCE_NOT_FOUND"


def test_read_only_enforcement(temp_dir, monkeypatch):
    # Mock write_file to raise PermissionError if called
    write_called = False

    def mock_write(*args, **kwargs):
        nonlocal write_called
        write_called = True
        raise PermissionError("Read-only mode")

    monkeypatch.setattr('src.bernstein.adapters.holmesgpt.write_file', mock_write)

    # Create a temporary output file (content irrelevant for this test)
    output_path = temp_dir / "output.json"
    output_path.write_text("{}")

    # Call the parser; should raise PermissionError due to read-only enforcement
    with pytest.raises(PermissionError):
        parse_output(str(output_path))

    # Ensure write was attempted (mocked)
    assert write_called


def test_env_isolation(monkeypatch):
    # Set environment variables
    monkeypatch.setenv("ALLOWED_KEY", "allowed_value")
    monkeypatch.setenv("DISALLOWED_KEY", "disallowed_value")
    monkeypatch.setenv("ANOTHER_DISALLOWED", "also_disallowed")

    filtered_env = build_filtered_env(["ALLOWED_KEY", "DISALLOWED_KEY", "ANOTHER_DISALLOWED"])

    # Assert that only ALLOWED_KEY is present
    assert "ALLOWED_KEY" in filtered_env
    assert filtered_env["ALLOWED_KEY"] == "allowed_value"
    assert "DISALLOWED_KEY" not in filtered_env
    assert "ANOTHER_DISALLOWED" not in filtered_env


def test_evidence_resolution(temp_dir):
    # Create evidence files
    evidence_dir = temp_dir / "evidence"
    evidence_dir.mkdir()
    file1 = evidence_dir / "file1.txt"
    file1.write_bytes(b"content1")
    hash1 = hashlib.sha256(b"content1").hexdigest()

    file2 = evidence_dir / "file2.txt"
    file2.write_bytes(b"content2")
    hash2 = hashlib.sha256(b"content2").hexdigest()

    # Create a verification request
    evidence_paths = [str(file1), str(file2)]
    result = verify_evidence(evidence_paths)

    # Assume result is a dict with "status": "OK" if hashes match
    assert result["status"] == "OK"
    # Also assert that the hashes match
    assert result["file_hashes"][str(file1)] == hash1
    assert result["file_hashes"][str(file2)] == hash2


def test_offline_reverify_mutated_blob(temp_dir):
    # Create evidence file
    evidence_dir = temp_dir / "evidence"
    evidence_dir.mkdir()
    file1 = evidence_dir / "file1.txt"
    original_content = b"original content"
    file1.write_bytes(original_content)
    hash1 = hashlib.sha256(original_content).hexdigest()

    # Mutate the file by changing one byte
    mutated_content = bytearray(original_content)
    mutated_content[0] = (mutated_content[0] + 1) % 256
    file1.write_bytes(bytes(mutated_content))

    # Verify offline (assuming there's a function that takes the original hash)
    result = verify_evidence([str(file1)], original_hash=hash1)

    # Expect refusal
    assert result["status"] == "REFUSED"
    assert "source_ref" in result
    assert str(file1) in result["source_ref"]