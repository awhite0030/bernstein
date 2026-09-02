from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bernstein.core.endpoints.certification import certified_roles_for_endpoint

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)


def select_volunteer_adapter(
    explicit_choice: str | None,
    *,
    workdir: Path,
    available_endpoints: Sequence[tuple[str, str]],
    required_role: str = "default",
) -> str:
    """Select the adapter for a volunteer task.

    If the donor explicitly passed an adapter name (e.g. ``--adapter=claude``),
    that choice is always honored.

    If no explicit adapter was chosen, volunteer mode defaults to a
    local/self-hosted model to protect the donor and the task from third-party
    API observability (see ``docs/volunteer/threat-model.md``). This function
    consults the ``available_endpoints`` list and checks if any local endpoint
    has a verified certification receipt for the ``required_role``. The first
    endpoint that does is selected, and we return the ``generic`` adapter
    (which routes to the local endpoints tier).

    If no local endpoint is certified for the role, the function falls back to
    the hardcoded default adapter (``aider``).

    Args:
        explicit_choice: The adapter name explicitly requested, or None.
        workdir: The local workdir, used to load certification receipts.
        available_endpoints: Sequence of ``(base_url, model)`` pairs for
            configured local endpoints.
        required_role: The role the endpoint must be certified for (defaults to "default").

    Returns:
        The string name of the adapter to use (to be passed to ``get_adapter``).
    """
    if explicit_choice is not None:
        return explicit_choice

    for base_url, model in available_endpoints:
        certified = certified_roles_for_endpoint(workdir, base_url, model)
        if required_role in certified:
            # We found a local endpoint certified for the role. The local-model tier
            # is driven by the generic adapter configured to point to it.
            return "generic"

    # Fall back to a default provider adapter if no local endpoint is available.
    return "aider"
