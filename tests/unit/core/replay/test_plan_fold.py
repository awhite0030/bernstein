from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bernstein.core.orchestration.schedule_projection import (
    TaskNode,
    canonical_graph_bytes,
)
from bernstein.core.replay.journal import EVENT_PLAN_AMENDMENT
from bernstein.core.replay.plan_fold import rebuild_task_graph


@st.composite
def generate_task_node_data(draw: st.DrawFn) -> dict[str, Any]:
    return {
        "id": draw(st.text(min_size=1, max_size=10)),
        "role": draw(st.text()),
        "title": draw(st.text()),
        "depends_on": draw(st.lists(st.text(min_size=1, max_size=10), max_size=3)),
    }


@st.composite
def generate_plan_graph_full_event(draw: st.DrawFn) -> dict[str, Any]:
    nodes = draw(st.lists(generate_task_node_data(), min_size=1, max_size=5))
    return {
        "event": "plan.graph.full",
        "nodes": nodes,
    }


@st.composite
def generate_amendment_event(draw: st.DrawFn, valid_task_ids: list[str]) -> dict[str, Any]:
    if not valid_task_ids:
        invalidates = []
    else:
        # subset of valid task ids
        invalidates = draw(st.lists(st.sampled_from(valid_task_ids), min_size=0, max_size=len(valid_task_ids)))
        invalidates = list(set(invalidates))  # unique

    return {
        "event": EVENT_PLAN_AMENDMENT,
        "invalidates": invalidates,
    }


@st.composite
def generate_journal_sequence(draw: st.DrawFn) -> list[dict[str, Any]]:
    # Start with a plan.graph.full event
    seq: list[dict[str, Any]] = [draw(generate_plan_graph_full_event())]

    # We collect current valid task ids
    current_ids = [str(n["id"]) for n in seq[0]["nodes"]]

    num_amendments = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_amendments):
        amendment = draw(generate_amendment_event(current_ids))
        seq.append(amendment)
        for invalid in amendment["invalidates"]:
            if invalid in current_ids:
                current_ids.remove(invalid)

    return seq


@given(generate_journal_sequence())
def test_fold_deterministic_and_total(events: list[dict[str, Any]]) -> None:
    """Property test: deterministic and total. Folding identical prefix yields identical graphs."""
    events_a = list(events)  # shallow copy
    events_b = list(events)

    # Total: Does not raise error
    result_a = rebuild_task_graph(events_a)
    result_b = rebuild_task_graph(events_b)

    # Deterministic: Identical bytes
    assert result_a == result_b


@given(generate_plan_graph_full_event())
def test_fold_prefix_reproduces_graph(plan_event: dict[str, Any]) -> None:
    """Folding a prefix that contains no amendment reproduces exactly the graph the producer recorded, byte for byte."""
    result = rebuild_task_graph([plan_event])

    # Produce the slice-1 digest bytes
    nodes: list[TaskNode] = []
    for n in plan_event["nodes"]:
        nodes.append(
            TaskNode(
                task_id=str(n["id"]),
                role=str(n["role"]),
                title="",
                description="",
                depends_on=tuple(sorted(str(d) for d in n["depends_on"])),
            )
        )

    # the function rebuild_task_graph builds dict mapping id -> TaskNode, so only the LAST node for each id survives.
    # We must replicate this logic to get the EXACT expected bytes.
    nodes_by_id: dict[str, TaskNode] = {}
    for node in nodes:
        nodes_by_id[node.task_id] = node

    expected_bytes = canonical_graph_bytes(nodes_by_id.values())

    assert result == expected_bytes


def test_amendment_keeps_completed_tasks_not_invalidated() -> None:
    """An amendment event applied to a prefix keeps every completed task that the amendment does not invalidate; a test asserts the surviving set by name, not by count."""
    events: list[dict[str, Any]] = [
        {
            "event": "plan.graph.full",
            "nodes": [
                {"id": "t1", "role": "a", "title": "T1", "depends_on": []},
                {"id": "t2", "role": "b", "title": "T2", "depends_on": ["t1"]},
                {"id": "t3", "role": "c", "title": "T3", "depends_on": ["t1"]},
            ],
        },
        {"event": EVENT_PLAN_AMENDMENT, "invalidates": ["t2"]},
    ]

    result_bytes = rebuild_task_graph(events)
    assert result_bytes is not None

    parsed = json.loads(result_bytes)
    assert "nodes" in parsed

    surviving_task_ids = set(n["task_id"] for n in parsed["nodes"])
    # Asserting the surviving set by name, not by count
    assert surviving_task_ids == {"t1", "t3"}


def test_amendment_rejects_replacement_graph() -> None:
    """An amendment names what it invalidates; a test asserts the fold rejects an amendment that carries a whole replacement graph."""
    events: list[dict[str, Any]] = [
        {"event": "plan.graph.full", "nodes": [{"id": "t1", "role": "a", "title": "T1", "depends_on": []}]},
        {
            "event": EVENT_PLAN_AMENDMENT,
            "invalidates": ["t1"],
            "nodes": [{"id": "t2", "role": "b", "title": "T2", "depends_on": []}],
        },
    ]

    with pytest.raises(ValueError, match="Amendment carries a replacement graph instead of invalidating tasks"):
        rebuild_task_graph(events)


def test_fold_truncated_prefix_yields_graph() -> None:
    """Folding a truncated prefix yields the graph as of that point, not an error."""
    events: list[dict[str, Any]] = [
        {
            "event": "plan.graph.full",
            "nodes": [
                {"id": "t1", "role": "a", "title": "T1", "depends_on": []},
                {"id": "t2", "role": "b", "title": "T2", "depends_on": ["t1"]},
            ],
        },
        {"event": EVENT_PLAN_AMENDMENT, "invalidates": ["t2"]},
    ]

    # Truncate to just the first event
    truncated_events = events[:1]

    result_bytes = rebuild_task_graph(truncated_events)
    assert result_bytes is not None

    parsed = json.loads(result_bytes)
    surviving_task_ids = set(n["task_id"] for n in parsed["nodes"])

    assert surviving_task_ids == {"t1", "t2"}
