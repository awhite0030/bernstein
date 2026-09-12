"""Autopilot state machine for the volunteer-workers program."""

from __future__ import annotations

import json
import logging
import signal
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import types
    from pathlib import Path

logger = logging.getLogger(__name__)


class Task:
    """An abstract task representation."""

    def __init__(self, id: str, content: Any = None) -> None:
        self.id = id
        self.content = content


class TaskResult:
    """An abstract task result representation."""

    def __init__(self, output: Any = None) -> None:
        self.output = output


class TaskSource(Protocol):
    """Protocol for a source of tasks for the autopilot loop to process."""

    def claim_next(self) -> Task | None: ...
    def run(self, task: Task) -> TaskResult: ...
    def submit(self, task: Task, result: TaskResult) -> None: ...
    def release(self, task: Task) -> None: ...


class AutopilotLoop:
    """State machine driving the volunteer claim->run->submit->repeat loop.

    Handles SIGINT gracefully by finishing in-flight tasks instead of
    exiting immediately, and uses a local ledger to avoid duplicate claims.
    """

    def __init__(self, source: TaskSource, ledger_path: Path) -> None:
        self._source = source
        self._ledger_path = ledger_path
        self._stop_requested = False
        self._original_sigint: Any = signal.SIG_DFL

    def _setup_signal_handler(self) -> None:
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_sigint)

    def _restore_signal_handler(self) -> None:
        signal.signal(signal.SIGINT, self._original_sigint)

    def _handle_sigint(self, signum: int, frame: types.FrameType | None) -> None:
        logger.info("SIGINT received, stopping autopilot loop after current task.")
        self._stop_requested = True

    def _has_been_claimed(self, task_id: str) -> bool:
        if not self._ledger_path.exists():
            return False
        with self._ledger_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if record.get("task_id") == task_id:
                        return True
                except json.JSONDecodeError:
                    continue
        return False

    def _append_to_ledger(self, task_id: str) -> None:
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger_path.open("a", encoding="utf-8") as f:
            json.dump({"task_id": task_id}, f)
            f.write("\n")

    def run_loop(self) -> None:
        """Run the autopilot loop until stopped by SIGINT or out of tasks."""
        self._setup_signal_handler()
        try:
            while not self._stop_requested:
                task = self._source.claim_next()
                if task is None:
                    break

                if self._has_been_claimed(task.id):
                    self._source.release(task)
                    continue

                # Record claim before starting work
                self._append_to_ledger(task.id)

                try:
                    result = self._source.run(task)
                    self._source.submit(task, result)
                except Exception as exc:
                    logger.exception("Task %s failed: %s", task.id, exc)
                    self._source.release(task)
        finally:
            self._restore_signal_handler()
