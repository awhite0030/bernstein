from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable, Static


@dataclass(frozen=True)
class VolunteerProjectEntry:
    """Summary entry for the project list table.

    Attributes:
        repo: Repository URL or name.
        name: Human-readable name.
        task_label: The label used to identify tasks (e.g., 'volunteer-ok').
        local_ok: Whether the project allows local model solving.
        demand: A string or indicator of task demand (if applicable).
    """

    repo: str
    name: str
    task_label: str
    local_ok: bool
    demand: str


@dataclass(frozen=True)
class VolunteerStatusSummary:
    """Detailed summary of a specific volunteer project.

    Attributes:
        repo: Repository URL.
        name: Human-readable name.
        requirements: Full requirements description.
        manifest_digest: The SHA-256 digest of the manifest.
        allowed_paths: List of allowed paths.
        egress_hosts: List of allowed egress hosts.
        topics: List of project topics.
        active_tasks: Count of currently active tasks.
        budget_consumption: String describing budget usage (e.g., '10%').
    """

    repo: str
    name: str
    requirements: str
    manifest_digest: str
    allowed_paths: list[str]
    egress_hosts: list[str]
    topics: list[str]
    active_tasks: int
    budget_consumption: str


class VolunteerJoinAction(Message):
    """Message sent when a user attempts to join a volunteer project."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        super().__init__()


class VolunteerLeaveAction(Message):
    """Message sent when a user attempts to leave a volunteer project."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        super().__init__()


class VolunteerFilterChanged(Message):
    """Message sent when filters are updated in the browser."""

    def __init__(
        self,
        topics: list[str] | None,
        languages: list[str] | None,
        local_ok_only: bool,
        min_size: str | None,
    ) -> None:
        self.topics = topics
        self.languages = languages
        self.local_ok_only = local_ok_only
        self.min_size = min_size
        super().__init__()


class VolunteerBrowserPanel(Static):
    """Two-pane widget for discovering and joining volunteer projects.

    Left Pane: DataTable showing a list of available projects.
    Right Pane: Detailed view of the selected project's requirements and policy.
    """

    DEFAULT_CSS = """
    VolunteerBrowserPanel {
        height: 1fr;
        width: 1fr;
        border: tall $primary 30%;
    }

    #browser-container {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
    }

    #project-list {
        height: 100%;
        border-right: solid $surface-darken-1;
    }

    #project-details {
        height: 100%;
        padding: 1 2;
        overflow-y: scroll;
    }

    .detail-section {
        margin-bottom: 1;
    }

    .section-title {
        text-style: bold underline;
        color: $accent;
    }

    .detail-label {
        color: $text-muted;
    }

    .detail-value {
        color: $text;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._projects: list[VolunteerProjectEntry] = []
        self._summaries: dict[str, VolunteerStatusSummary] = {}
        self._filtered_projects: list[VolunteerProjectEntry] = []

    def update_data(
        self,
        projects: list[VolunteerProjectEntry],
        summaries: dict[str, VolunteerStatusSummary],
    ) -> None:
        """Update the widget with the latest project data.

        Args:
            projects: List of summary entries for the table.
            summaries: Mapping of repo URL to detailed status summaries.
        """
        self._projects = projects
        self._summaries = summaries
        self._filtered_projects = projects.copy()
        self.refresh_list()

    def refresh_list(self) -> None:
        """Repopulate the project list table."""
        try:
            list_table = self.query_one("#project-list", DataTable)  # type: ignore
            list_table.clear()
            for project in self._filtered_projects:
                list_table.add_row(
                    project.name,
                    project.task_label,
                    "✓" if project.local_ok else "✗",
                    project.demand,
                    key=project.repo,
                )
        except Exception:
            # Table may not be ready yet during mount
            pass

    def apply_filters(
        self,
        topics: list[str] | None = None,
        languages: list[str] | None = None,
        local_ok_only: bool = False,
        min_size: str | None = None,
    ) -> None:
        """Filter projects based on criteria.

        Args:
            topics: Filter by project topics.
            languages: Filter by language topic.
            local_ok_only: Only show projects allowing local model solving.
            min_size: Filter by size (e.g. 'large').
        """
        self._filtered_projects = self._projects.copy()

        if local_ok_only:
            self._filtered_projects = [p for p in self._filtered_projects if p.local_ok]

        if topics:
            # Filter by topics - this would need proper integration with manifest data
            # For now we'll filter based on demand field as a placeholder
            self._filtered_projects = [
                p
                for p in self._filtered_projects
                if any(topic in p.demand.lower() for topic in [t.lower() for t in topics])
            ]

        if languages:
            # Filter by languages - similar to topics
            self._filtered_projects = [
                p
                for p in self._filtered_projects
                if any(lang in p.demand.lower() for lang in [lc.lower() for lc in languages])
            ]

        if min_size:
            # Filter by size - looking in demand field
            self._filtered_projects = [p for p in self._filtered_projects if min_size.lower() in p.demand.lower()]

        self.refresh_list()

    def on_mount(self) -> None:
        """Initialize the two-pane layout."""
        container = Static(id="browser-container")
        self.mount(container)

        list_table = DataTable(id="project-list")  # type: ignore
        list_table.add_columns("Project", "Label", "Local", "Dem")
        list_table.cursor_type = "row"
        list_table.zebra_stripes = True

        details_pane = Static(id="project-details")

        container.mount(list_table, details_pane)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle selection of a project in the list."""
        try:
            repo = str(event.row_key.value)
            if repo in self._summaries:
                self._render_details(self._summaries[repo])
        except Exception:
            # Ignore errors during initial mount
            pass

    def _render_details(self, summary: VolunteerStatusSummary) -> None:
        """Render detailed view for a project.

        Args:
            summary: The summary to display.
        """
        try:
            pane = self.query_one("#project-details", Static)

            content = Text()
            content.append(f"{summary.name}\n", style="bold cyan")
            content.append(f"Repo: {summary.repo}\n\n", style="dim")

            # Requirements
            content.append("Requirements\n", style="section-title")
            content.append(f"{summary.requirements}\n\n")

            # Policy Info
            content.append("Policy\n", style="section-title")
            content.append(f"Manifest: {summary.manifest_digest}\n")
            content.append(f"Allowed Paths: {', '.join(summary.allowed_paths) or 'all'}\n")
            content.append(f"Egress Hosts: {', '.join(summary.egress_hosts) or 'none'}\n\n")

            # Metadata
            content.append("Metadata\n", style="section-title")
            content.append(f"Topics: {', '.join(summary.topics)}\n")
            content.append(f"Active Tasks: {summary.active_tasks}\n")
            content.append(f"Budget: {summary.budget_consumption}\n")

            pane.update(content)
        except Exception:
            # Ignore errors during initial mount
            pass
