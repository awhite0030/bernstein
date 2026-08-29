# RunGraphReceipt Sealing and Verification (#3760)

## Summary

Implemented run-graph receipt sealing and verification system to capture the pairing of every fan-out branch with its spine's current head hash. The system seals receipts into the lineage spine with Ed25519 JWS signatures and verifies them by re-deriving the graph, walking every spine, and checking the Ed25519 signature.

## Key Features

- **Sealing**: Captures the complete graph state (all branches with their head SHAs and spine head hashes) and signs it with an Ed25519 key
- **Verification**: Re-derives the graph, validates each spine, and checks the Ed25519 signature
- **Fail-closed**: Empty fan-outs report "empty" status and never pass trivially
- **Branch identification**: Failed verification names the offending branch in the error reason
- **Schema versioning**: Receipt schema version is versioned for future wire-format changes

## Changes

- Added `src/bernstein/core/lineage/run_graph_receipt.py` with:
  - `RunGraphReceipt` sealed receipt dataclass
  - `RunGraphVerifyResult` verification outcome dataclass  
  - `build_run_graph_receipt()` function to create sealed receipts
  - `verify_run_graph_receipt()` function to validate receipts
- Added comprehensive tests in `tests/unit/lineage/test_run_graph_receipt.py` covering:
  - Golden path: successful verification of a 3-branch receipt
  - Tampering detection: verifying that modifications fail and identify the branch
  - Empty fan-out: proper handling of zero-branch receipts
  - Missing worktree: detection of cleaned-up worktrees
  - Head SHA divergence: catching worktree state changes
  - Serialization roundtrip: verifying serialization preserves all data
  - Signature validation: ensuring receipts without valid signatures fail

## Benefits

1. **Deterministic validation**: Verification re-derives the exact same graph state
2. **Cryptographic integrity**: Ed25519 signatures prevent tampering
3. **Full auditability**: Every branch verification is logged and reported
4. **Fail-safe design**: Nothing passes silently when there are issues
5. **Backward compatibility**: Uses existing primitives from `run_graph.py` and `spine.py`

## Testing

All tests pass with:
```bash
uv run pytest tests/unit/lineage/test_run_graph_receipt.py -x -q
```

The implementation follows the existing code patterns and maintains consistency with the verification philosophy established in the codebase (e.g., the verdict receipt system).