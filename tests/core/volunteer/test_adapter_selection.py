from pathlib import Path
from bernstein.core.volunteer.adapter_selection import select_volunteer_adapter
import pytest

def test_select_volunteer_adapter_explicit(tmp_path: Path):
    assert select_volunteer_adapter(
        "claude",
        workdir=tmp_path,
        available_endpoints=[("http://localhost:11434/v1", "llama3")]
    ) == "claude"

def test_select_volunteer_adapter_fallback_no_endpoints(tmp_path: Path):
    assert select_volunteer_adapter(
        None,
        workdir=tmp_path,
        available_endpoints=[]
    ) == "aider"

# We'll need a mock for `certified_roles_for_endpoint` to test the generic path.
def test_select_volunteer_adapter_local_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "bernstein.core.volunteer.adapter_selection.certified_roles_for_endpoint",
        lambda w, b, m: frozenset({"default", "linter"})
    )
    assert select_volunteer_adapter(
        None,
        workdir=tmp_path,
        available_endpoints=[("http://localhost:11434/v1", "llama3")]
    ) == "generic"

def test_select_volunteer_adapter_local_not_certified_for_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "bernstein.core.volunteer.adapter_selection.certified_roles_for_endpoint",
        lambda w, b, m: frozenset({"linter"})
    )
    assert select_volunteer_adapter(
        None,
        workdir=tmp_path,
        available_endpoints=[("http://localhost:11434/v1", "llama3")],
        required_role="default"
    ) == "aider"
