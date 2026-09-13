with open("tests/unit/cli/test_govern_audit_cmd.py", "r") as f:
    content = f.read()

content = content.replace(
    'assert results[0]["kind"] == "measured"',
    'assert results[0]["kind"] == "fail"'
)
content = content.replace(
    'assert results[1]["kind"] == "not_measurable"',
    'assert results[1]["kind"] == "notApplicable"'
)

with open("tests/unit/cli/test_govern_audit_cmd.py", "w") as f:
    f.write(content)
