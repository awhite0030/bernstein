"""Run-graph receipts for lineage verification (#3760).

A run-graph receipt captures the pairing of every fan-out branch with its
spine's current head hash, seals it into the lineage spine, and signs it with
an Ed25519 key. Verification re-derives the graph, walks every spine, and
checks the Ed25519 signature. Empty fan-outs (no branches) are an explicit
"empty" status - they never trivially pass (fail-closed).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bernstein.core.lineage.identity import AgentCard, sign_detached, verify_detached
from bernstein.core.lineage.run_graph import RunGraphNode, RunGraphNodeStatus
from bernstein.core.lineage.spine import LineageSpine, SpineStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

#: Version stamped into every run-graph receipt. Bump only on a wire-format change.
RUN_GRAPH_RECEIPT_SCHEMA_VERSION = 1

#: Lineage run id under which every run-graph receipt is anchored, kept separate
#: so run-graph receipts never interleave with verdict or other receipts.
RUN_GRAPH_RECEIPT_RUN_ID = "run-graph-receipt"

_RECEIPT_ACTOR = "bernstein.run_graph_receipt"


@dataclass(frozen=True, slots=True)
class RunGraphReceipt:
    """A sealed run-graph receipt.

    The body (everything the signature covers) binds the nodes tuple, the
    computed root hash, and the timestamp. The signature is an Ed25519 JWS
    detached (RFC 7515 + RFC 7797) over the canonical body bytes. The public
    key is included so a verifier needs no external key store - the card is the
    receipt.
    """

    schema_version: int
    nodes: tuple[RunGraphNode, ...]
    root_hash: str
    timestamp: int
    signature: str
    signer_public_key_pem: str

    def canonical_bytes(self) -> bytes:
        """Canonical bytes for signing.

        The canonical bytes are the deterministic JSON encoding of the body
        (schema_version, nodes, root_hash, timestamp). The ``signature`` and
        ``signer_public_key_pem`` are not part of the signed payload.
        """
        body = {
            "schema_version": self.schema_version,
            "nodes": [
                {
                    "session_id": node.session_id,
                    "head_sha": node.head_sha,
                    "run_id": node.run_id,
                    "spine_head_hash": node.spine_head_hash,
                    "status": node.status.value,
                }
                for node in self.nodes
            ],
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
        }
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def signing_input(self) -> bytes:
        """The bytes that the Ed25519 signature covers.

        The signing input follows the b64=false detached-JWS contract: the
        protected header (which includes the kid) followed by a dot and the
        payload bytes. This matches the pattern in :mod:`bernstein.core.lineage.identity`.
        """
        header = {"alg": "EdDSA", "kid": "run-graph-receipt", "b64": False, "crit": ["b64"]}
        protected = (
            base64.urlsafe_b64encode(
                json.dumps(header, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            )
            .rstrip(b"=")
            .decode("ascii")
        )
        return protected.encode("ascii") + b"." + self.canonical_bytes()

    def to_dict(self) -> dict:
        """Return a dict representation for serialization."""
        return {
            "schema_version": self.schema_version,
            "nodes": [
                {
                    "session_id": node.session_id,
                    "head_sha": node.head_sha,
                    "run_id": node.run_id,
                    "spine_head_hash": node.spine_head_hash,
                    "status": node.status.value,
                }
                for node in self.nodes
            ],
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "signer_public_key_pem": self.signer_public_key_pem,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunGraphReceipt:
        """Construct a RunGraphReceipt from a dict.

        This is primarily for testing and verification where receipts are
        serialized to JSON files.
        """
        nodes = []
        for node_data in data["nodes"]:
            nodes.append(
                RunGraphNode(
                    session_id=node_data["session_id"],
                    head_sha=node_data["head_sha"],
                    run_id=node_data["run_id"],
                    spine_head_hash=node_data["spine_head_hash"],
                    status=RunGraphNodeStatus(node_data["status"]),
                )
            )
        return cls(
            schema_version=data["schema_version"],
            nodes=tuple(nodes),
            root_hash=data["root_hash"],
            timestamp=data["timestamp"],
            signature=data["signature"],
            signer_public_key_pem=data["signer_public_key_pem"],
        )

    def to_dict_without_signature(self) -> dict:
        """Return a dict representation without the signature for verification."""
        return {
            "schema_version": self.schema_version,
            "nodes": [
                {
                    "session_id": node.session_id,
                    "head_sha": node.head_sha,
                    "run_id": node.run_id,
                    "spine_head_hash": node.spine_head_hash,
                    "status": node.status.value,
                }
                for node in self.nodes
            ],
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class RunGraphVerifyResult:
    """Outcome of an offline run-graph receipt verification."""

    ok: bool
    status: str  # "ok", "tampered", "empty", "diverged", "missing", etc.
    reason: str
    receipt: RunGraphReceipt | None


def build_run_graph_receipt(
    repo_root: Path,
    lineage_root: Path,
    run_ids: Mapping[str, str],
    hmac_key: bytes,
    signing_key_pem: str,
    timestamp: int,
    head_sha_resolver: Callable[[Path], str | None] | None = None,
) -> RunGraphReceipt:
    """Build and seal a run-graph receipt.

    This function follows the re-derive-don't-trust pattern: it calls
    :func:`build_run_graph` to get the graph, then creates the receipt with
    an Ed25519 signature over the canonical body bytes.
    """
    from bernstein.core.lineage.run_graph import build_run_graph

    if head_sha_resolver is None:
        from bernstein.core.worktrees.classifier import _git_head_sha

        head_sha_resolver = _git_head_sha

    # Build the graph using the existing run_graph function
    graph = build_run_graph(
        repo_root,
        run_ids=run_ids,
        lineage_root=lineage_root,
        hmac_key=hmac_key,
        head_sha_resolver=head_sha_resolver,
    )

    # Extract public key from the signing key
    # The signing_key_pem is a private key PEM, we need the corresponding public key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = serialization.load_pem_private_key(signing_key_pem.encode("ascii"), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("signing key must be an Ed25519 private key")

    public_key_pem = (
        private_key.public_key()
        .public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )

    # Create the receipt
    receipt = RunGraphReceipt(
        schema_version=RUN_GRAPH_RECEIPT_SCHEMA_VERSION,
        nodes=graph.nodes,
        root_hash=graph.root_hash,
        timestamp=timestamp,
        signature="",  # Will be filled by signature
        signer_public_key_pem=public_key_pem,
    )

    # Sign the receipt using the existing sign_detached function
    signature = sign_detached(receipt.canonical_bytes(), signing_key_pem, kid="run-graph-receipt")

    # Create the final receipt with signature
    final_receipt = RunGraphReceipt(
        schema_version=receipt.schema_version,
        nodes=receipt.nodes,
        root_hash=receipt.root_hash,
        timestamp=receipt.timestamp,
        signature=signature,
        signer_public_key_pem=public_key_pem,
    )

    # Anchor the receipt in the lineage spine
    spine = LineageSpine(lineage_root, run_id=RUN_GRAPH_RECEIPT_RUN_ID, hmac_key=hmac_key)
    artifact_path = f"receipts/{graph.root_hash}.json"
    spine.record(
        artifact_path=artifact_path,
        content=final_receipt.canonical_bytes(),
        actor=_RECEIPT_ACTOR,
        step_id=graph.root_hash,
        model="run-graph-receipt-builder",
        timestamp=timestamp,
    )

    return final_receipt


def verify_run_graph_receipt(
    receipt: RunGraphReceipt,
    repo_root: Path,
    lineage_root: Path,
    hmac_key: bytes,
    head_sha_resolver: Callable[[Path], str | None] | None = None,
) -> RunGraphVerifyResult:
    """Verify a run-graph receipt.

    This function re-derives the graph, walks every spine, and checks the
    Ed25519 signature. Empty fan-outs (no branches) report status="empty"
    and never pass trivially (fail-closed).
    """
    if head_sha_resolver is None:
        from bernstein.core.worktrees.classifier import _git_head_sha

        head_sha_resolver = _git_head_sha

    # Check for empty fan-out
    if not receipt.nodes:
        return RunGraphVerifyResult(
            ok=False,
            status="empty",
            reason="run graph receipt has no branches (empty fan-out)",
            receipt=receipt,
        )

    # Check Ed25519 signature using the existing verify_detached function
    card = AgentCard(
        agent_id="run-graph-receipt",
        kid="run-graph-receipt",
        public_key_pem=receipt.signer_public_key_pem,
    )
    if not verify_detached(receipt.canonical_bytes(), receipt.signature, card):
        return RunGraphVerifyResult(
            ok=False,
            status="tampered",
            reason="Ed25519 signature verification failed",
            receipt=receipt,
        )

    # Re-derive the graph
    from bernstein.core.lineage.run_graph import build_run_graph, compute_root_hash

    run_ids = {}
    for node in receipt.nodes:
        if node.run_id is not None:
            run_ids[node.session_id] = node.run_id

    rederived_graph = build_run_graph(
        repo_root,
        run_ids=run_ids,
        lineage_root=lineage_root,
        hmac_key=hmac_key,
        head_sha_resolver=head_sha_resolver,
    )

    # Check that re-derived graph matches receipt
    if rederived_graph.nodes != receipt.nodes:
        # Find the differing node
        for i, (receipt_node, rederived_node) in enumerate(zip(receipt.nodes, rederived_graph.nodes, strict=True)):
            if receipt_node != rederived_node:
                diverged_reason = (
                    f"node {i} ({receipt_node.session_id}) diverges: receipt={receipt_node}, rederived={rederived_node}"
                )
                return RunGraphVerifyResult(
                    ok=False,
                    status="diverged",
                    reason=diverged_reason,
                    receipt=receipt,
                )
        # If order changed but nodes are same, that's still a failure
        return RunGraphVerifyResult(
            ok=False,
            status="diverged",
            reason="graph nodes differ between receipt and re-derivation",
            receipt=receipt,
        )

    # Check root hash
    expected_root_hash = compute_root_hash(receipt.nodes)
    if expected_root_hash != receipt.root_hash:
        return RunGraphVerifyResult(
            ok=False,
            status="diverged",
            reason=f"root hash mismatch: expected={expected_root_hash}, receipt={receipt.root_hash}",
            receipt=receipt,
        )

    # Verify each branch's spine
    for node in receipt.nodes:
        if node.run_id is None:
            continue

        spine = LineageSpine(lineage_root, run_id=node.run_id, hmac_key=hmac_key)
        spine_result = spine.verify()

        if spine_result.status is not SpineStatus.OK:
            missing_detail = ""
            if spine_result.status is SpineStatus.NO_ENTRIES:
                missing_detail = " (no entries in spine)"
            elif spine_result.status is SpineStatus.SEAL_ONLY:
                missing_detail = " (spine contains only journal seal)"
            elif spine_result.status is SpineStatus.TAMPERED:
                missing_detail = f" (tampered: {spine_result.errors})"

            # For empty spines, report as missing (fail-closed behavior)
            branch_reason = (
                f"branch {node.session_id} spine verification failed: {spine_result.status.value}{missing_detail}"
            )
            if spine_result.status is SpineStatus.NO_ENTRIES:
                return RunGraphVerifyResult(
                    ok=False,
                    status="missing",
                    reason=branch_reason,
                    receipt=receipt,
                )
            # For other spine status issues, report as diverged
            else:
                return RunGraphVerifyResult(
                    ok=False,
                    status="diverged",
                    reason=branch_reason,
                    receipt=receipt,
                )

        # Re-derive the spine's head hash and compare
        if spine.head_hash() != node.spine_head_hash:
            head_mismatch_reason = (
                f"branch {node.session_id} spine head hash mismatch: "
                f"expected={spine.head_hash()}, receipt={node.spine_head_hash}"
            )
            return RunGraphVerifyResult(
                ok=False,
                status="diverged",
                reason=head_mismatch_reason,
                receipt=receipt,
            )

    # All checks passed
    return RunGraphVerifyResult(
        ok=True,
        status="ok",
        reason="",
        receipt=receipt,
    )


__all__ = [
    "RUN_GRAPH_RECEIPT_RUN_ID",
    "RUN_GRAPH_RECEIPT_SCHEMA_VERSION",
    "RunGraphReceipt",
    "RunGraphVerifyResult",
    "build_run_graph_receipt",
    "verify_run_graph_receipt",
]
