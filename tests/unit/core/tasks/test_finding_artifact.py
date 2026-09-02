import pytest

from bernstein.core.tasks.artifacts import ArtifactKind, CanonicalisationError, artifact_content_hash


def test_finding_identity_stable_across_line_shift():
    # The exact same finding, but startLine moved from 10 to 11
    finding_at_line_10 = {
        "ruleId": "G101",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 10, "snippet": {"text": "password = 'hunter2'"}},
                }
            }
        ],
        "tool": "gitleaks",
        "tool_version": "8.18.0",
        "pinned_ruleset_or_feed_digest": "sha256:abc",
        "invocation_argv_hash": "sha256:def",
        "target": "src/app.py",
    }
    finding_at_line_11 = {
        "ruleId": "G101",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 11, "snippet": {"text": "password = 'hunter2'"}},  # Line shifted!
                }
            }
        ],
        "tool": "gitleaks",
        "tool_version": "8.18.0",
        "pinned_ruleset_or_feed_digest": "sha256:abc",
        "invocation_argv_hash": "sha256:def",
        "target": "src/app.py",
    }

    hash_10 = artifact_content_hash(ArtifactKind.FINDING, finding_at_line_10)
    hash_11 = artifact_content_hash(ArtifactKind.FINDING, finding_at_line_11)

    # Cosmetic line shift must not change the hash
    assert hash_10 == hash_11


def test_finding_identity_changes_when_snippet_changes():
    finding_1 = {
        "ruleId": "G101",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 10, "snippet": {"text": "password = 'hunter2'"}},
                }
            }
        ],
        "tool": "gitleaks",
        "tool_version": "1",
        "pinned_ruleset_or_feed_digest": "1",
        "invocation_argv_hash": "1",
        "target": "a",
    }
    finding_2 = {
        "ruleId": "G101",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 10, "snippet": {"text": "password = 'hunter3'"}},  # Snippet changed!
                }
            }
        ],
        "tool": "gitleaks",
        "tool_version": "1",
        "pinned_ruleset_or_feed_digest": "1",
        "invocation_argv_hash": "1",
        "target": "a",
    }

    hash_1 = artifact_content_hash(ArtifactKind.FINDING, finding_1)
    hash_2 = artifact_content_hash(ArtifactKind.FINDING, finding_2)

    # Rule is not just ignoring everything; snippet matters
    assert hash_1 != hash_2

def test_finding_rejects_malformed_input():
    # The malformed-input case from issue #3699 (empty mapping) asserting rejection.
    # Previously, this incorrectly returned a valid identity.
    with pytest.raises(CanonicalisationError, match="missing required field result.ruleId"):
        artifact_content_hash(ArtifactKind.FINDING, {})

def test_finding_entry_points_produce_same_address():
    import json

    from bernstein.core.evidence.run_artifacts import ArtifactPayload

    finding = {
        "ruleId": "G101",
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 10, "snippet": {"text": "password = 'hunter2'"}},
                }
            }
        ],
        "tool": "gitleaks",
        "tool_version": "8.18.0",
        "pinned_ruleset_or_feed_digest": "sha256:abc",
        "invocation_argv_hash": "sha256:def",
        "target": "src/app.py",
    }

    # Entry point 1: Tasks / artifacts
    # Note: For artifacts to return the same hash, it must hash the preimage JSON bytes.
    # Since artifact_content_hash wraps canonical_bytes with sha256, it evaluates:
    # "sha256:" + sha256(_canonical_finding_bytes(finding))
    # where _canonical_finding_bytes returns canonical_json_bytes(address_preimage).
    # This precisely matches what `address` is defined as.
    task_hash = artifact_content_hash(ArtifactKind.FINDING, finding)

    # Entry point 2: Evidence / run_artifacts
    payload = ArtifactPayload.finding(
        finding,
        tool=str(finding["tool"]),
        tool_version=str(finding["tool_version"]),
        pinned_ruleset_or_feed_digest=str(finding["pinned_ruleset_or_feed_digest"]),
        invocation_argv_hash=str(finding["invocation_argv_hash"]),
        target=str(finding["target"])
    )
    payload_json = json.loads(payload.canonical_bytes())
    evidence_address = payload_json["address"]

    # The hash computed by the task artifacts pipeline MUST be the same address
    # embedded by the evidence artifacts pipeline.
    assert task_hash == evidence_address
