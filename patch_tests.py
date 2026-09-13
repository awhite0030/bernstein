import re

with open("tests/unit/cli/test_govern_audit_cmd.py", "r") as f:
    content = f.read()

content = content.replace("--json-output", "--format json")
content = content.replace("--format json json", "--format json") # in case of double replacement

with open("tests/unit/cli/test_govern_audit_cmd.py", "w") as f:
    f.write(content)
