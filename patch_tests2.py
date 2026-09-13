import re

with open("tests/unit/cli/test_govern_audit_cmd.py", "r") as f:
    content = f.read()

content = content.replace("--format json", "--format", 100)

with open("tests/unit/cli/test_govern_audit_cmd.py", "w") as f:
    f.write(content)
