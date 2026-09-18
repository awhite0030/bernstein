from pathlib import Path

from bernstein.core.security.governance import (
    RoleBindings,
    decide_access,
)
from bernstein.core.security.policy_diff import replay_decisions


def test_replay_decisions(tmp_path: Path) -> None:
    old_bindings = RoleBindings(
        group_to_role={"group1": "admin", "group2": "viewer"},
        role_permissions={
            "admin": ("read", "write"),
            "viewer": ("read",),
        },
    ).sign(b"key")

    new_bindings = RoleBindings(
        group_to_role={"group1": "admin", "group2": "viewer"},
        role_permissions={
            "admin": ("read",),  # write removed
            "viewer": ("read", "write"),  # write added
        },
    ).sign(b"key")

    lineage_root = tmp_path / "lineage"
    hmac_key = b"hmac_key"
    run_id = "run-1"

    d1 = decide_access(
        run_id=run_id,
        lineage_root=lineage_root,
        hmac_key=hmac_key,
        subject="alice",
        idp_groups=("group1",),
        action="write",
        bindings=old_bindings,
        now=1000,
    )

    d2 = decide_access(
        run_id=run_id,
        lineage_root=lineage_root,
        hmac_key=hmac_key,
        subject="bob",
        idp_groups=("group2",),
        action="write",
        bindings=old_bindings,
        now=1000,
    )

    corpus = [d1, d2]
    diff = replay_decisions(corpus, old_bindings, new_bindings)

    assert diff.allow_to_deny == 1
    assert diff.deny_to_allow == 1
