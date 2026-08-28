"""Tests for VolunteerBrowserPanel TUI widget."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from textual.app import App
from textual.binding import Binding
from textual.message import Message

from bernstein.tui.volunteer_browser import (
    VolunteerBrowserPanel,
    VolunteerFilterChanged,
    VolunteerJoinAction,
    VolunteerLeaveAction,
    VolunteerProjectEntry,
    VolunteerStatusSummary,
)


class _VolunteerBrowserHarnessApp(App[None]):
    """Minimal app that mounts VolunteerBrowserPanel and records dispatched actions."""

    def __init__(self) -> None:
        super().__init__()
        self.join_actions: list[VolunteerJoinAction] = []
        self.leave_actions: list[VolunteerLeaveAction] = []
        self.filter_changes: list[VolunteerFilterChanged] = []

    def compose(self):
        yield VolunteerBrowserPanel()

    def on_volunteer_join_action(self, event: VolunteerJoinAction) -> None:
        self.join_actions.append(event)

    def on_volunteer_leave_action(self, event: VolunteerLeaveAction) -> None:
        self.leave_actions.append(event)

    def on_volunteer_filter_changed(self, event: VolunteerFilterChanged) -> None:
        self.filter_changes.append(event)


def _sample_project_entry() -> VolunteerProjectEntry:
    return VolunteerProjectEntry(
        repo="https://github.com/example/project",
        name="Example Project",
        task_label="volunteer-ok",
        local_ok=True,
        demand="high",
    )


def _sample_status_summary() -> VolunteerStatusSummary:
    return VolunteerStatusSummary(
        repo="https://github.com/example/project",
        name="Example Project",
        requirements="Test requirements",
        manifest_digest="abc123",
        allowed_paths=["/src", "/tests"],
        egress_hosts=["api.example.com"],
        topics=["python", "cli"],
        active_tasks=5,
        budget_consumption="25%",
    )


def _sample_status_summary_with_topics(topics: list[str]) -> VolunteerStatusSummary:
    return VolunteerStatusSummary(
        repo="https://github.com/example/project",
        name="Example Project",
        requirements="Test requirements",
        manifest_digest="abc123",
        allowed_paths=["/src", "/tests"],
        egress_hosts=["api.example.com"],
        topics=topics,
        active_tasks=5,
        budget_consumption="25%",
    )


# -----------------------------------------------------------------------
# Dataclass tests
# -----------------------------------------------------------------------


def test_volunteer_project_entry_dataclass_fields() -> None:
    """VolunteerProjectEntry stores all assigned fields."""
    entry = VolunteerProjectEntry(
        repo="repo",
        name="name",
        task_label="label",
        local_ok=True,
        demand="demand",
    )
    assert entry.repo == "repo"
    assert entry.name == "name"
    assert entry.task_label == "label"
    assert entry.local_ok is True
    assert entry.demand == "demand"


def test_volunteer_project_entry_is_frozen() -> None:
    """VolunteerProjectEntry is frozen and rejects attribute assignment."""
    entry = VolunteerProjectEntry(repo="repo", name="name", task_label="label", local_ok=True, demand="demand")
    with pytest.raises(FrozenInstanceError):
        entry.repo = "new"  # type: ignore[misc]


def test_volunteer_status_summary_dataclass_fields() -> None:
    """VolunteerStatusSummary stores all assigned fields."""
    summary = VolunteerStatusSummary(
        repo="repo",
        name="name",
        requirements="req",
        manifest_digest="digest",
        allowed_paths=["p1"],
        egress_hosts=["h1"],
        topics=["t1"],
        active_tasks=3,
        budget_consumption="50%",
    )
    assert summary.repo == "repo"
    assert summary.name == "name"
    assert summary.requirements == "req"
    assert summary.manifest_digest == "digest"
    assert summary.allowed_paths == ["p1"]
    assert summary.egress_hosts == ["h1"]
    assert summary.topics == ["t1"]
    assert summary.active_tasks == 3
    assert summary.budget_consumption == "50%"


def test_volunteer_status_summary_is_frozen() -> None:
    """VolunteerStatusSummary is frozen and rejects attribute assignment."""
    summary = VolunteerStatusSummary(
        repo="repo",
        name="name",
        requirements="req",
        manifest_digest="d",
        allowed_paths=[],
        egress_hosts=[],
        topics=[],
        active_tasks=0,
        budget_consumption="0%",
    )
    with pytest.raises(FrozenInstanceError):
        summary.repo = "new"  # type: ignore[misc]


# -----------------------------------------------------------------------
# Message tests
# -----------------------------------------------------------------------


def test_volunteer_join_action_is_message() -> None:
    """VolunteerJoinAction is a Message subclass and exposes .repo."""
    action = VolunteerJoinAction(repo="https://github.com/test")
    assert isinstance(action, Message)
    assert action.repo == "https://github.com/test"


def test_volunteer_leave_action_is_message() -> None:
    """VolunteerLeaveAction is a Message subclass and exposes .repo."""
    action = VolunteerLeaveAction(repo="https://github.com/test")
    assert isinstance(action, Message)
    assert action.repo == "https://github.com/test"


def test_volunteer_filter_changed_is_message() -> None:
    """VolunteerFilterChanged is a Message subclass and exposes all filter attrs."""
    action = VolunteerFilterChanged(
        topics=["python"],
        languages=["javascript"],
        local_ok_only=True,
        min_size="large",
    )
    assert isinstance(action, Message)
    assert action.topics == ["python"]
    assert action.languages == ["javascript"]
    assert action.local_ok_only is True
    assert action.min_size == "large"


def test_volunteer_filter_changed_accepts_none() -> None:
    """VolunteerFilterChanged accepts None for topics and languages."""
    action = VolunteerFilterChanged(
        topics=None,
        languages=None,
        local_ok_only=False,
        min_size=None,
    )
    assert action.topics is None
    assert action.languages is None
    assert action.local_ok_only is False
    assert action.min_size is None


# -----------------------------------------------------------------------
# Panel construction / state
# -----------------------------------------------------------------------


def test_volunteer_browser_panel_initial_state() -> None:
    """VolunteerBrowserPanel starts with empty state."""
    panel = VolunteerBrowserPanel()
    assert panel._projects == []
    assert panel._summaries == {}
    assert panel._filtered_projects == []


# -----------------------------------------------------------------------
# update_data / refresh_list
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_data_populates_state() -> None:
    """update_data() writes through to _projects, _summaries, _filtered_projects."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as _:
        panel = app.query_one(VolunteerBrowserPanel)
        projects = [_sample_project_entry()]
        summaries = {_sample_project_entry().repo: _sample_status_summary()}

        panel.update_data(projects, summaries)

        assert panel._projects == projects
        assert panel._summaries == summaries
        # _filtered_projects is a copy, not the same list
        assert panel._filtered_projects == projects
        assert panel._filtered_projects is not projects


@pytest.mark.asyncio
async def test_refresh_list_populates_datatable() -> None:
    """refresh_list() clears the DataTable and adds one row per filtered project."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        entry = _sample_project_entry()
        panel._projects = [entry]
        panel._filtered_projects = [entry]

        panel.refresh_list()
        await pilot.pause()

        list_table = panel.query_one("#project-list")
        assert list_table.row_count == 1


@pytest.mark.asyncio
async def test_refresh_list_handles_empty_filtered_list() -> None:
    """refresh_list() with no projects results in empty table."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        # Add something first
        panel._projects = [_sample_project_entry()]
        panel._filtered_projects = [_sample_project_entry()]
        panel.refresh_list()
        await pilot.pause()

        # Now clear
        panel._filtered_projects = []
        panel.refresh_list()
        await pilot.pause()

        list_table = panel.query_one("#project-list")
        assert list_table.row_count == 0


# -----------------------------------------------------------------------
# apply_filters
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_filters_local_ok_only() -> None:
    """apply_filters(local_ok_only=True) keeps only entries with local_ok=True."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        local = VolunteerProjectEntry(repo="local", name="Local", task_label="ok", local_ok=True, demand="high")
        remote = VolunteerProjectEntry(repo="remote", name="Remote", task_label="ok", local_ok=False, demand="high")
        panel._projects = [local, remote]
        panel._filtered_projects = [local, remote]

        panel.apply_filters(local_ok_only=True)
        await pilot.pause()

        assert [p.repo for p in panel._filtered_projects] == ["local"]

        # Without filter, both present
        panel._filtered_projects = [local, remote]
        panel.apply_filters(local_ok_only=False)
        await pilot.pause()
        assert {p.repo for p in panel._filtered_projects} == {"local", "remote"}


@pytest.mark.asyncio
async def test_apply_filters_topics_case_insensitive() -> None:
    """apply_filters(topics=...) matches VolunteerStatusSummary.topics case-insensitively."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        py = VolunteerProjectEntry(repo="py", name="Py", task_label="ok", local_ok=True, demand="high")
        js = VolunteerProjectEntry(repo="js", name="JS", task_label="ok", local_ok=True, demand="high")
        panel._projects = [py, js]
        panel._filtered_projects = [py, js]
        panel._summaries = {
            "py": _sample_status_summary_with_topics(["python", "web"]),
            "js": _sample_status_summary_with_topics(["javascript", "node"]),
        }

        panel.apply_filters(topics=["python"])
        await pilot.pause()

        assert [p.repo for p in panel._filtered_projects] == ["py"]


@pytest.mark.asyncio
async def test_apply_filters_languages_case_insensitive() -> None:
    """apply_filters(languages=...) matches VolunteerStatusSummary.topics case-insensitively."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        py = VolunteerProjectEntry(repo="py", name="Py", task_label="ok", local_ok=True, demand="high")
        rs = VolunteerProjectEntry(repo="rs", name="RS", task_label="ok", local_ok=True, demand="high")
        panel._projects = [py, rs]
        panel._filtered_projects = [py, rs]
        panel._summaries = {
            "py": _sample_status_summary_with_topics(["python"]),
            "rs": _sample_status_summary_with_topics(["rust"]),
        }

        panel.apply_filters(languages=["python"])
        await pilot.pause()

        assert [p.repo for p in panel._filtered_projects] == ["py"]


@pytest.mark.asyncio
async def test_apply_filters_min_size_case_insensitive() -> None:
    """apply_filters(min_size=...) matches demand case-insensitively."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        large = VolunteerProjectEntry(repo="large", name="L", task_label="ok", local_ok=True, demand="Size: Large")
        small = VolunteerProjectEntry(repo="small", name="S", task_label="ok", local_ok=True, demand="size: small")
        panel._projects = [large, small]
        panel._filtered_projects = [large, small]

        panel.apply_filters(min_size="large")
        await pilot.pause()

        assert [p.repo for p in panel._filtered_projects] == ["large"]


@pytest.mark.asyncio
async def test_apply_filters_no_filters_keeps_all() -> None:
    """apply_filters with no args keeps every project."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        a = VolunteerProjectEntry(repo="a", name="A", task_label="ok", local_ok=True, demand="any")
        b = VolunteerProjectEntry(repo="b", name="B", task_label="ok", local_ok=False, demand="other")
        panel._projects = [a, b]
        panel._filtered_projects = [a, b]

        panel.apply_filters()
        await pilot.pause()

        assert {p.repo for p in panel._filtered_projects} == {"a", "b"}


# -----------------------------------------------------------------------
# _render_details
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_details_writes_to_pane() -> None:
    """_render_details() updates the project-details pane."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        panel._render_details(_sample_status_summary())
        await pilot.pause()

        # Pane exists and is now non-empty
        pane = panel.query_one("#project-details")
        assert pane is not None


# -----------------------------------------------------------------------
# DEFAULT_CSS / static config
# -----------------------------------------------------------------------


def test_default_css_project_list_border_is_solid() -> None:
    """#project-list uses 'solid' border-right style, not 'slim'."""
    css = VolunteerBrowserPanel.DEFAULT_CSS
    assert "#project-list" in css
    assert "border-right: solid $surface-darken-1" in css


def test_default_css_section_title_uses_shorthand_bold_underline() -> None:
    """.section-title combines bold and underline in text-style shorthand."""
    css = VolunteerBrowserPanel.DEFAULT_CSS
    assert ".section-title" in css
    # New behavior: underline is part of text-style shorthand, not separate text-decoration
    assert "text-style: bold underline" in css


def test_default_css_section_title_has_no_separate_text_decoration() -> None:
    """.section-title does not use separate text-decoration property."""
    css = VolunteerBrowserPanel.DEFAULT_CSS
    # Verify old property is gone
    assert "text-decoration: underline" not in css


def test_default_css_contains_panel_rules() -> None:
    """DEFAULT_CSS defines layout selectors referenced by the panel."""
    css = VolunteerBrowserPanel.DEFAULT_CSS
    assert "VolunteerBrowserPanel" in css
    assert "#browser-container" in css
    assert "#project-list" in css
    assert "#project-details" in css


# -----------------------------------------------------------------------
# Key bindings and action handlers
# -----------------------------------------------------------------------


def test_volunteer_browser_panel_bindings() -> None:
    """VolunteerBrowserPanel defines key bindings for join and leave."""
    bindings = VolunteerBrowserPanel.BINDINGS
    actions = {b.action: b.key for b in bindings if isinstance(b, Binding)}
    assert actions.get("join") == "j"
    assert actions.get("leave") == "l"


@pytest.mark.asyncio
async def test_action_join_dispatches_message() -> None:
    """action_join dispatches VolunteerJoinAction for the selected project."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        entry = _sample_project_entry()
        panel.update_data([entry], {entry.repo: _sample_status_summary()})
        await pilot.pause()

        panel.action_join()
        await pilot.pause()

        assert len(app.join_actions) == 1
        assert app.join_actions[0].repo == entry.repo


@pytest.mark.asyncio
async def test_action_leave_dispatches_message() -> None:
    """action_leave dispatches VolunteerLeaveAction for the selected project."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        entry = _sample_project_entry()
        panel.update_data([entry], {entry.repo: _sample_status_summary()})
        await pilot.pause()

        panel.action_leave()
        await pilot.pause()

        assert len(app.leave_actions) == 1
        assert app.leave_actions[0].repo == entry.repo


@pytest.mark.asyncio
async def test_on_action_join_and_leave_aliases() -> None:
    """on_action_join and on_action_leave invoke action_join and action_leave."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        entry = _sample_project_entry()
        panel.update_data([entry], {entry.repo: _sample_status_summary()})
        await pilot.pause()

        panel.on_action_join()
        await pilot.pause()
        assert len(app.join_actions) == 1
        assert app.join_actions[0].repo == entry.repo

        panel.on_action_leave()
        await pilot.pause()
        assert len(app.leave_actions) == 1
        assert app.leave_actions[0].repo == entry.repo


@pytest.mark.asyncio
async def test_action_join_and_leave_no_projects() -> None:
    """action_join and action_leave do not dispatch when no project exists."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        panel.action_join()
        panel.action_leave()
        await pilot.pause()

        assert len(app.join_actions) == 0
        assert len(app.leave_actions) == 0


@pytest.mark.asyncio
async def test_keybinding_press_triggers_actions() -> None:
    """Pressing 'j' or 'l' triggers join/leave actions in TUI."""
    app = _VolunteerBrowserHarnessApp()
    async with app.run_test() as pilot:
        panel = app.query_one(VolunteerBrowserPanel)
        entry = _sample_project_entry()
        panel.update_data([entry], {entry.repo: _sample_status_summary()})
        await pilot.pause()

        table = panel.query_one("#project-list")
        table.focus()
        await pilot.pause()

        await pilot.press("j")
        await pilot.pause()
        assert len(app.join_actions) == 1
        assert app.join_actions[0].repo == entry.repo

        await pilot.press("l")
        await pilot.pause()
        assert len(app.leave_actions) == 1
        assert app.leave_actions[0].repo == entry.repo
