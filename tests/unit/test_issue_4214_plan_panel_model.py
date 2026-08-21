"""Regression tests for issue #4214.

``bernstein run --model <M>`` printed a plan-approval panel that always
named ``sonnet`` and priced the run with it, whatever ``--model`` was
passed: ``_confirm_run`` (the entry point that builds the synthetic plan
shown for approval) never received the CLI's resolved model, so
``configure_plan_models`` only ever saw a seed's ``model:`` key -- and not
at all for an inline goal with no seed. ``_estimate_task_cost`` then fell
back to the "sonnet" complexity default, disagreeing with the model the
run actually used (confirmed correct in the post-approval "Cost estimate:"
line and the run's own journal).

Pinned here, against the *rendered* panel (not internal state):

* The task table and the Agent Assignments box name the resolved
  ``--model``, not the "sonnet" fallback.
* Cost is computed from that model.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import pytest
from bernstein.core.plan_approval import configure_plan_models

from bernstein.cli.helpers import console
from bernstein.cli.run_bootstrap import _confirm_run


@pytest.fixture(autouse=True)
def _reset_plan_models() -> object:
    """Ensure the module-global seed defaults never leak between tests."""
    configure_plan_models(None)
    yield
    configure_plan_models(None)


def _render_confirm_panel(model_override: str | None) -> str:
    """Run ``_confirm_run`` for an inline goal and capture the panel text.

    Non-TTY (pytest has no real terminal), so ``_confirm_run`` renders and
    auto-approves without blocking on a keypress.
    """
    with console.capture() as cap:
        approved = _confirm_run(goal="fix the two one-liners", seed_file=None, model_override=model_override)
    assert approved is True
    return cap.get()


def test_panel_names_and_prices_the_explicit_model_override() -> None:
    """An explicit --model that differs from the default reaches the panel."""
    out = _render_confirm_panel("opus")

    assert "opus" in out, out
    # The task table's Model column and the Agent Assignments box both read
    # est.model; neither should fall back to the hardcoded default.
    assert "sonnet" not in out.lower(), out


def test_panel_names_default_model_when_no_override_given() -> None:
    """Baseline: with no --model, the panel still falls back sensibly."""
    out = _render_confirm_panel(None)

    assert "sonnet" in out.lower(), out


def test_panel_model_matches_configure_plan_models_default() -> None:
    """The resolved model reaches every TaskCostEstimate construction site.

    Mirrors the dry-run path's pattern of threading ``model_override``
    straight into the estimate, so the panel and the post-approval
    ``Cost estimate:`` line agree for the same run.
    """
    from bernstein.core.models import Task
    from bernstein.core.plan_approval import _estimate_task_cost

    _confirm_run(goal="fix the two one-liners", seed_file=None, model_override="opus")

    est = _estimate_task_cost(Task(id="t1", title="do work", description="", role="manager"))
    assert est.model == "opus"
    assert est.estimated_cost_usd > 0.0
