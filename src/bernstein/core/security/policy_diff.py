from dataclasses import dataclass

from bernstein.core.security.governance import (
    _BUDGET_ACTION,
    GovernanceDecision,
    RoleBindings,
    _access_inputs_hash,
    _candidate_roles,
    _role_grants,
)


@dataclass(frozen=True)
class DecisionDiff:
    """Outcome of replaying a corpus of decisions against a candidate policy.

    Attributes:
        allow_to_deny: Number of decisions that changed from allow to deny.
        deny_to_allow: Number of decisions that changed from deny to allow.
    """

    allow_to_deny: int
    deny_to_allow: int


def replay_decisions(
    corpus: list[GovernanceDecision],
    old_policy: RoleBindings,
    new_policy: RoleBindings,
) -> DecisionDiff:
    """Replay a corpus of decisions against a candidate policy.

    The original policy is required to resolve the `inputs_hash` back to the role.

    Args:
        corpus: The list of recorded GovernanceDecision to replay.
        old_policy: The original RoleBindings the corpus was evaluated against.
        new_policy: The new RoleBindings to evaluate them against.

    Returns:
        The DecisionDiff with the counts of changed verdicts.
    """
    allow_to_deny = 0
    deny_to_allow = 0

    for decision in corpus:
        if decision.action == _BUDGET_ACTION:
            continue

        resolved_role = None
        for role in _candidate_roles(old_policy):
            if _access_inputs_hash(role=role, action=decision.action, bindings=old_policy) == decision.inputs_hash:
                resolved_role = role
                break

        if resolved_role is None:
            # Hash wasn't produced by this old_policy (or policy differs). Skip it.
            continue

        new_verdict = "allow" if _role_grants(resolved_role, decision.action, new_policy) else "deny"
        if decision.verdict == "allow" and new_verdict == "deny":
            allow_to_deny += 1
        elif decision.verdict == "deny" and new_verdict == "allow":
            deny_to_allow += 1

    return DecisionDiff(allow_to_deny=allow_to_deny, deny_to_allow=deny_to_allow)
