import re
from pathlib import Path

path = Path("tests/unit/test_graduation.py")
content = path.read_text()

# We need to remove all tests related to GraduationStore's event recording because those methods have been deleted.
test_store_search = '''    def test_record_task_event_success(self, tmp_path: Path) -> None:
        store = GraduationStore(tmp_path)
        record = store.record_task_event("run-1", success=True, task_id="t1", duration_s=10.0)
        assert record.current_metrics().tasks_completed == 1
        assert record.current_metrics().consecutive_failures == 0

    def test_record_task_event_failure(self, tmp_path: Path) -> None:
        store = GraduationStore(tmp_path)
        record = store.record_task_event("run-1", success=False, task_id="t1")
        assert record.current_metrics().tasks_failed == 1
        assert record.current_metrics().consecutive_failures == 1

    def test_record_task_event_resets_consecutive_on_success(self, tmp_path: Path) -> None:
        store = GraduationStore(tmp_path)
        store.record_task_event("run-1", success=False, task_id="t1")
        store.record_task_event("run-1", success=False, task_id="t2")
        record = store.record_task_event("run-1", success=True, task_id="t3")
        assert record.current_metrics().consecutive_failures == 0
        assert record.current_metrics().tasks_completed == 1

    def test_metrics_appended_to_jsonl(self, tmp_path: Path) -> None:
        store = GraduationStore(tmp_path)
        store.record_task_event("run-1", success=True, task_id="t1", cost_usd=0.10)
        store.record_task_event("run-1", success=False, task_id="t2")
        metrics_file = tmp_path / "metrics" / "graduation.jsonl"
        assert metrics_file.exists()
        lines = [json.loads(ln) for ln in metrics_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2
        assert lines[0]["task_id"] == "t1"
        assert lines[0]["success"] is True
        assert lines[1]["success"] is False

    def test_record_promotion_writes_to_jsonl(self, tmp_path: Path) -> None:
        store = GraduationStore(tmp_path)
        record = store.get_or_create("run-1")
        ev = GraduationEvaluator()
        ev.promote(record, reason="manual", promoted_by="alice")
        store.save(record)
        store.record_promotion(record)
        metrics_file = tmp_path / "metrics" / "graduation.jsonl"
        lines = [json.loads(ln) for ln in metrics_file.read_text().splitlines() if ln.strip()]
        promotion = next((l for l in lines if l.get("type") == "promotion"), None)
        assert promotion is not None
        assert promotion["from_stage"] == "sandbox"
        assert promotion["to_stage"] == "shadow"'''

# Use regex to find and remove if they still exist.
import re
content = re.sub(r'    def test_record_task_event_success.*?(?=\n\n# ---------------------------------------------------------------------------)', '', content, flags=re.DOTALL)
path.write_text(content)
