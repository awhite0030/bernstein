import json
import signal
from pathlib import Path

from bernstein.core.volunteer.autopilot import AutopilotLoop, Task, TaskResult, TaskSource


class MockTaskSource(TaskSource):
    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = tasks
        self.ran_tasks: list[str] = []
        self.submitted_tasks: list[str] = []
        self.released_tasks: list[str] = []

    def claim_next(self) -> Task | None:
        if self.tasks:
            return self.tasks.pop(0)
        return None

    def run(self, task: Task) -> TaskResult:
        if task.id == "fail_me":
            raise RuntimeError("Task failed")
        self.ran_tasks.append(task.id)
        return TaskResult(output="done")

    def submit(self, task: Task, result: TaskResult) -> None:
        self.submitted_tasks.append(task.id)

    def release(self, task: Task) -> None:
        self.released_tasks.append(task.id)


def test_autopilot_loop_success(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    tasks = [Task("t1"), Task("t2")]
    source = MockTaskSource(tasks)

    loop = AutopilotLoop(source, ledger_path)
    loop.run_loop()

    assert source.ran_tasks == ["t1", "t2"]
    assert source.submitted_tasks == ["t1", "t2"]

    # Ledger should have recorded both claims
    records = []
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))

    assert records == [{"task_id": "t1"}, {"task_id": "t2"}]


def test_autopilot_loop_duplicate_claim(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as f:
        f.write('{"task_id": "t1"}\n')

    tasks = [Task("t1"), Task("t2")]
    source = MockTaskSource(tasks)

    loop = AutopilotLoop(source, ledger_path)
    loop.run_loop()

    # t1 was claimed in ledger, so it should be released and skipped
    assert source.ran_tasks == ["t2"]
    assert source.released_tasks == ["t1"]


def test_autopilot_loop_task_failure(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    tasks = [Task("t1"), Task("fail_me"), Task("t3")]
    source = MockTaskSource(tasks)

    loop = AutopilotLoop(source, ledger_path)
    loop.run_loop()

    # t1 and t3 succeed, fail_me fails and is released
    assert source.ran_tasks == ["t1", "t3"]
    assert source.released_tasks == ["fail_me"]


def test_autopilot_loop_sigint(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    tasks = [Task("t1"), Task("t2"), Task("t3")]

    class SigintSource(MockTaskSource):
        def run(self, task: Task) -> TaskResult:
            if task.id == "t1":
                # Simulate a SIGINT being sent during the first task's execution
                import os

                os.kill(os.getpid(), signal.SIGINT)
            return super().run(task)

    source = SigintSource(tasks)

    loop = AutopilotLoop(source, ledger_path)
    loop.run_loop()

    # Should run and submit t1, but stop before claiming t2
    assert source.ran_tasks == ["t1"]
    assert source.submitted_tasks == ["t1"]

    # t2 and t3 should still be in the source queue (unclaimed)
    assert len(source.tasks) == 2
