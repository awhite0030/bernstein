import os
import subprocess
import sys
from pathlib import Path
import resource

def test_memory_guard_not_applied_to_xdist_controller(tmp_path: Path):
    """Ensure the xdist controller process doesn't get the memory limit.

    The limit should only apply to workers, or to the single process when
    not using xdist.
    """
    plugin_path = tmp_path / "conftest.py"
    plugin_content = '''
import pytest
import platform
import os

if platform.system() != "Windows":
    import resource

def pytest_configure(config):
    if platform.system() == "Windows":
        return

    is_worker = hasattr(config, "workerinput")
    soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    role = "worker" if is_worker else "controller"
    print(f"\\nLIMIT_{role}_{soft}\\n")
'''
    plugin_path.write_text(plugin_content)

    test_path = tmp_path / "test_dummy.py"
    test_path.write_text("def test_dummy(): pass\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())

    # We want to load the root conftest which currently applies the limit at import time
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-n", "2", "-p", "no:cacheprovider", "-p", "tests.conftest", "-s"],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
        env=env
    )

    out = result.stdout

    orig_soft, _ = resource.getrlimit(resource.RLIMIT_AS)

    print("STDOUT:")
    print(out)

    assert "LIMIT_controller" in out

    lines = out.splitlines()
    for line in lines:
        if line.startswith("LIMIT_controller_"):
            val_str = line.split("_")[-1]
            val = int(val_str)
            assert val == orig_soft, f"Controller got limited: {val} instead of {orig_soft}"
        elif line.startswith("LIMIT_worker_"):
            val_str = line.split("_")[-1]
            val = int(val_str)
            assert val != orig_soft, f"Worker got unlimited: {val}"
            assert val == 2 * 1024 * 1024 * 1024, f"Worker got wrong limit: {val}"
