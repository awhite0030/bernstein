import re
from pathlib import Path

path = Path("tests/integration/test_first_run_graduation_surface.py")
content = path.read_text()
content = content.replace("    from bernstein.core.quality.graduation import GraduationRecord, GraduationStage", "")

path.write_text("from bernstein.core.quality.graduation import GraduationRecord, GraduationStage\n" + content)
