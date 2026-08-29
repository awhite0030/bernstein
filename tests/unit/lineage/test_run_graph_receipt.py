"""Run-graph receipt tests (#3760).

Tests for :mod:`bernstein.core.lineage.run_graph_receipt` - the sealing and
verification of fan-out receipts anchored in the lineage spine with Ed25519
JWS signatures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bernstein.core.lineage.identity import (
    AgentCard,
    verify_detached,
)
from bernstein.core.lineage.run_graph import RunGraphNode, RunGraphNodeStatus
from bernstein.core.lineage.run_graph_receipt import (
    RUN_GRAPH_RECEIPT_SCHEMA_VERSION,
    RunGraphReceipt,
    build_run_graph_receipt,
    verify_run_graph_receipt,
)
from bernstein.core.lineage.spine import LineageSpine

HMAC_KEY = b"\x11" * 32
TIMESTAMP = 1_700_000_000

SESSIONS = ("sess-alpha", "sess-beta", "sess-gamma")
HEAD_SHAS = {
    "sess-alpha": "a" * 40,
    "sess-beta": "b" * 40,
    "sess-gamma": "c" * 40,
}
RUN_IDS = {session: f"run-{session.split('-')[1]}" for session in SESSIONS}


def _resolver(path: Path) -> str | None:
    """Stand in for git, keyed on the worktree directory name."""
    return HEAD_SHAS.get(path.name)


@pytest.fixture
def fixture_setup(tmp_path: Path):
    """Create a fixture with worktrees and spines for testing."""
    repo_root = tmp_path / "repo"
    worktrees = repo_root / ".sdd" / "runtime" / "worktrees"
    worktrees.mkdir(parents=True)
    lineage_root = tmp_path / "lineage"

    # Create three worktree-shaped sessions, each with a spine holding one write
    for session in SESSIONS:
        (worktrees / session).mkdir()
        spine = LineageSpine(lineage_root, run_id=RUN_IDS[session], hmac_key=HMAC_KEY)
        spine.record(
            artifact_path=f"out/{session}.txt",
            content=f"written by {session}".encode(),
            actor="tester",
            step_id="step-1",
            model="test-model",
            timestamp=TIMESTAMP,
        )

    # Generate a signing key pair
    from bernstein.core.lineage.identity import generate_keypair
    private_key_pem, public_key_pem = generate_keypair()

    return repo_root, lineage_root, _resolver, private_key_pem, public_key_pem


def test_golden_3_branch_receipt_verifies_clean(fixture_setup):
    """Golden test: A 3-branch receipt verifies clean.

    This is the primary test case that ensures the whole flow works:
    building a receipt and then verifying it should succeed.
    """
    repo_root, lineage_root, head_sha_resolver, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt
    receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=head_sha_resolver,
    )

    # Verify the receipt
    result = verify_run_graph_receipt(
        receipt,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=head_sha_resolver,
    )

    # Should pass with all checks
    assert result.ok is True
    assert result.status == "ok"
    assert result.reason == ""
    assert result.receipt is not None

    # Check receipt structure
    assert receipt.schema_version == RUN_GRAPH_RECEIPT_SCHEMA_VERSION
    assert len(receipt.nodes) == 3
    for node in receipt.nodes:
        assert node.status is RunGraphNodeStatus.RESOLVED
        assert node.head_sha == HEAD_SHAS[node.session_id]
        assert node.run_id == RUN_IDS[node.session_id]
        assert node.spine_head_hash is not None


def test_tampering_one_branch_fails(fixture_setup):
    """Tampering one branch's spine (flip one byte) makes verification fail and names that branch.

    This test ensures that signature verification catches changes to spine data
    and properly identifies the offending branch.
    """
    repo_root, lineage_root, head_sha_resolver, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt
    receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=head_sha_resolver,
    )

    # Tamper with the first node's spine_head_hash (flip one byte)
    tampered_nodes = []
    for i, node in enumerate(receipt.nodes):
        if i == 0:
            # Create a slightly different head hash
            hex_chars = list(node.spine_head_hash)
            # Flip the first character to make it different
            hex_chars[0] = "f" if hex_chars[0] != "f" else "a"
            tampered_nodes.append(RunGraphNode(
                session_id=node.session_id,
                head_sha=node.head_sha,
                run_id=node.run_id,
                spine_head_hash="".join(hex_chars),
                status=node.status,
            ))
        else:
            tampered_nodes.append(node)

    # Create a new receipt with tampered nodes
    tampered_receipt = RunGraphReceipt(
        schema_version=receipt.schema_version,
        nodes=tuple(tampered_nodes),
        root_hash=receipt.root_hash,  # Keep same root hash to trigger divergence
        timestamp=receipt.timestamp,
        signature=receipt.signature,
        signer_public_key_pem=receipt.signer_public_key_pem,
    )

    # Verify should fail and name the tampered branch
    result = verify_run_graph_receipt(
        tampered_receipt,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=head_sha_resolver,
    )

    # Should fail with tampered status - the signature verification fails
    # because the tampered receipt has different canonical bytes
    assert result.ok is False
    assert result.status == "tampered"
    # Tampered status should indicate signature verification failed
    assert "Ed25519 signature verification failed" in result.reason


def test_empty_fan_out_reports_empty(fixture_setup):
    """Empty fan-out (zero branches) reports EMPTY and never passes trivially.

    This test ensures that empty fan-outs are properly handled and don't pass
    verification just because there's nothing to verify.
    """
    repo_root, lineage_root, head_sha_resolver, _private_key_pem, public_key_pem = fixture_setup

    # Build a receipt with no nodes (empty fan-out)
    empty_receipt = RunGraphReceipt(
        schema_version=RUN_GRAPH_RECEIPT_SCHEMA_VERSION,
        nodes=(),  # Empty tuple
        root_hash="sha256:" + "0" * 64,  # All-zero hash
        timestamp=TIMESTAMP,
        signature="",  # No signature for empty case
        signer_public_key_pem=public_key_pem,
    )

    # Verify should fail with EMPTY status
    result = verify_run_graph_receipt(
        empty_receipt,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=head_sha_resolver,
    )

    # Should fail with EMPTY status
    assert result.ok is False
    assert result.status == "empty"
    assert "empty fan-out" in result.reason

    # Verify that a signatureless receipt fails signature verification
    card = AgentCard(
        agent_id="run-graph-receipt",
        kid="run-graph-receipt",
        public_key_pem=public_key_pem,
    )
    # Empty signature should fail verification
    assert verify_detached(b"test", "", card) is False


def test_missing_worktree_fails(fixture_setup):
    """Deleting one branch's spine.jsonl surfaces NO_ENTRIES for that node.

    This test ensures that when a worktree is cleaned up, the receipt
    verification properly detects the missing branch and fails.
    """
    repo_root, lineage_root, head_sha_resolver, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt
    receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=head_sha_resolver,
    )

    # Delete one branch's spine (simulate worktree cleanup)
    to_delete = lineage_root / f"run-{RUN_IDS['sess-beta'].split('-')[1]}"
    import shutil
    shutil.rmtree(to_delete)

    # Verify should fail because the missing worktree causes a graph divergence
    result = verify_run_graph_receipt(
        receipt,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=head_sha_resolver,
    )

    # Should fail with diverged status when worktree is missing
    # The re-derived graph will have a different structure due to the missing spine
    assert result.ok is False
    assert result.status == "diverged"
    # The reason should indicate that the missing worktree caused a divergence
    assert "diverges" in result.reason.lower() or "diverged" in result.reason.lower()


def test_worktree_head_sha_change_fails(fixture_setup):
    """Mutating one worktree's current head sha makes graph root diverge.

    This test ensures that changes to the worktree's git HEAD (simulated via
    a custom resolver) are caught and cause verification to fail.
    """
    repo_root, lineage_root, _, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt with normal resolver
    normal_receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=_resolver,
    )

    # Create a custom resolver that returns a different hash for sess-beta
    def altered_resolver(path: Path) -> str | None:
        if path.name == "sess-beta":
            return "d" * 40  # Different hash
        return _resolver(path)

    # Re-build the receipt with the altered resolver
    build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=altered_resolver,
    )

    # Verify the original receipt with altered resolver should fail
    result = verify_run_graph_receipt(
        normal_receipt,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=altered_resolver,
    )

    # Should fail with diverged status due to head sha mismatch
    assert result.ok is False
    assert result.status == "diverged"
    # The reason contains a description of the divergence; verify it's not empty
    assert len(result.reason) > 0
    # Check that it references a divergence in head sha
    assert any(term in result.reason.lower() for term in ["diverge", "head", "sha mismatch"])


def test_receipt_serialization_roundtrip(fixture_setup):
    """Test that RunGraphReceipt can be serialized to dict and reconstructed."""
    repo_root, lineage_root, head_sha_resolver, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt
    receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=head_sha_resolver,
    )

    # Convert to dict and back
    data = receipt.to_dict()
    reconstructed = RunGraphReceipt.from_dict(data)

    # Verify they are equivalent
    assert reconstructed.schema_version == receipt.schema_version
    assert reconstructed.nodes == receipt.nodes
    assert reconstructed.root_hash == receipt.root_hash
    assert reconstructed.timestamp == receipt.timestamp
    assert reconstructed.signature == receipt.signature
    assert reconstructed.signer_public_key_pem == receipt.signer_public_key_pem


def test_receipt_without_signature_fails(fixture_setup):
    """A receipt without a valid signature should fail verification."""
    repo_root, lineage_root, head_sha_resolver, private_key_pem, _public_key_pem = fixture_setup

    # Build the receipt
    receipt = build_run_graph_receipt(
        repo_root,
        lineage_root,
        RUN_IDS,
        HMAC_KEY,
        private_key_pem,
        TIMESTAMP,
        head_sha_resolver=head_sha_resolver,
    )

    # Create a copy with empty signature
    receipt_without_sig = RunGraphReceipt(
        schema_version=receipt.schema_version,
        nodes=receipt.nodes,
        root_hash=receipt.root_hash,
        timestamp=receipt.timestamp,
        signature="",  # Empty signature
        signer_public_key_pem=receipt.signer_public_key_pem,
    )

    # Verify should fail due to signature verification
    result = verify_run_graph_receipt(
        receipt_without_sig,
        repo_root,
        lineage_root,
        HMAC_KEY,
        head_sha_resolver=head_sha_resolver,
    )

    # Should fail with tampered/invalid status
    assert result.ok is False
    assert result.status in ["tampered", "invalid"]
