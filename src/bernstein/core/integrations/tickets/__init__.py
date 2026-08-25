"""Ticket import integrations for Bernstein.

This package exposes a single entry point, :func:`fetch_ticket`, which
inspects a ticket URL and dispatches to the appropriate provider module.
Provider modules (``linear``, ``github_issues``, ``jira``) are designed to
be importable without their credential environment variables present --
all env-var reads happen inside the fetch function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

__all__ = [
    "TicketAuthError",
    "TicketParseError",
    "TicketPayload",
    "TicketRateLimitError",
    "fetch_ticket",
]


Provider = Literal["linear", "github", "jira"]


@dataclass(frozen=True)
class TicketPayload:
    """Normalized ticket representation shared across providers."""

    id: str
    title: str
    description: str
    labels: tuple[str, ...] = field(default_factory=tuple)
    assignee: str | None = None
    url: str = ""
    source: Provider = "github"


class TicketAuthError(RuntimeError):
    """Raised when a provider cannot authenticate (missing or invalid creds)."""


class TicketParseError(RuntimeError):
    """Raised when a ticket URL cannot be parsed or the response is malformed."""


class TicketRateLimitError(RuntimeError):
    """Raised when a ticket provider rate-limits API requests.

    Carries metadata about the rate limit event so callers can handle
    rate limiting specially (e.g. implementing backoff or waiting).

    Attributes:
        provider: Provider name (e.g. 'github', 'linear', 'jira').
        wait_seconds: Seconds to wait before retrying.
        retry_count: Number of retries attempted so far.
        last_response_headers: HTTP response headers from the rate-limited response.
    """

    def __init__(
        self,
        provider: str,
        wait_seconds: float = 0.0,
        retry_count: int = 0,
        last_response_headers: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        self.provider: str = str(provider)
        self.wait_seconds: float = float(wait_seconds)
        self.retry_count: int = int(retry_count)
        self.last_response_headers: dict[str, Any] = (
            dict(last_response_headers) if last_response_headers is not None else {}
        )
        if message is None:
            message = (
                f"Rate limit exceeded for provider {self.provider!r}. "
                f"Wait {self.wait_seconds}s (retries: {self.retry_count})."
            )
        super().__init__(message)


_LINEAR_WEB = re.compile(
    r"^https?://linear\.app/(?P<workspace>[^/]+)/issue/(?P<key>[A-Z0-9]+-\d+)",
    re.IGNORECASE,
)
_LINEAR_SCHEME = re.compile(r"^linear://(?P<key>[A-Z0-9]+-\d+)", re.IGNORECASE)
_GITHUB_ISSUE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<num>\d+)",
    re.IGNORECASE,
)
_JIRA_BROWSE = re.compile(r"/browse/(?P<key>[A-Z][A-Z0-9_]+-\d+)", re.IGNORECASE)


def _classify(url: str) -> Provider:
    """Return the provider responsible for *url* or raise TicketParseError."""
    trimmed = url.strip()
    if _LINEAR_WEB.search(trimmed) or _LINEAR_SCHEME.search(trimmed):
        return "linear"
    if _GITHUB_ISSUE.search(trimmed):
        return "github"
    parsed = urlparse(trimmed)
    # Jira cloud: any https URL whose path contains /browse/KEY-123
    if parsed.scheme in {"http", "https"} and _JIRA_BROWSE.search(parsed.path):
        return "jira"
    raise TicketParseError(f"Unrecognized ticket URL shape: {url!r}")


def fetch_ticket(url: str) -> TicketPayload:
    """Fetch and normalize a ticket from a supported provider URL.

    Dispatches on the URL shape:

    * ``https://linear.app/{workspace}/issue/{KEY}`` or ``linear://KEY``
    * ``https://github.com/{owner}/{repo}/issues/{n}``
    * ``https://{domain}/browse/{KEY-N}`` (Jira cloud)

    Raises:
        TicketParseError: URL is not recognized or the response is malformed.
        TicketAuthError: provider credentials are missing or invalid.
        TicketRateLimitError: provider rate limit was exceeded.
    """
    provider = _classify(url)
    if provider == "linear":
        from bernstein.core.integrations.tickets import linear

        return linear.fetch_linear(url)
    if provider == "github":
        from bernstein.core.integrations.tickets import github_issues

        return github_issues.fetch_github_issue(url)
    # jira
    from bernstein.core.integrations.tickets import jira

    return jira.fetch_jira(url)
