"""Fold for recovering the task graph from journal events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bernstein.core.orchestration.schedule_projection import TaskNode, canonical_graph_bytes
from bernstein.core.replay.journal import EVENT_PLAN_AMENDMENT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def rebuild_task_graph(events: Iterable[Mapping[str, Any]]) -> bytes | None:
    """Fold chain events into a canonical task graph.

    Args:
        events: Journal rows in append order.

    Returns:
        The canonical task graph bytes (identical to schedule_projection.canonical_graph_bytes),
        or None if no graph is present.

    Raises:
        ValueError: If an amendment event carries a replacement graph.
    """
    nodes_by_id: dict[str, TaskNode] | None = None

    for row in events:
        event = str(row.get("event", ""))
        if event == "plan.graph.full":
            nodes = row.get("nodes")
            if isinstance(nodes, list):
                nodes_by_id = {}
                for n in cast("list[Any]", nodes):
                    if isinstance(n, dict):
                        # Use dict[str, Any] cast to help pyright
                        n_dict = cast("dict[str, Any]", n)
                        task_id = str(n_dict.get("id", ""))
                        role = str(n_dict.get("role", ""))
                        depends_on_list = n_dict.get("depends_on", [])
                        if isinstance(depends_on_list, list):
                            depends_on = tuple(
                                sorted(str(d) for d in cast("list[Any]", depends_on_list) if isinstance(d, str))
                            )
                        else:
                            depends_on = ()
                        nodes_by_id[task_id] = TaskNode(
                            task_id=task_id,
                            role=role,
                            title="",
                            description="",
                            depends_on=depends_on,
                        )
        elif event == EVENT_PLAN_AMENDMENT:
            if nodes_by_id is None:
                continue
            if "nodes" in row:
                raise ValueError("Amendment carries a replacement graph instead of invalidating tasks")
            invalidates = row.get("invalidates")
            if isinstance(invalidates, list):
                for invalid_task_id in cast("list[Any]", invalidates):
                    if isinstance(invalid_task_id, str):
                        nodes_by_id.pop(invalid_task_id, None)

    if nodes_by_id is None:
        return None

    return canonical_graph_bytes(nodes_by_id.values())


__all__ = ["rebuild_task_graph"]
