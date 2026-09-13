with open("src/bernstein/cli/commands/governance_cmd.py", "r") as f:
    content = f.read()

content = content.replace(
    '"kind": outcome.verdict.value,',
    '"kind": "pass" if outcome.passed else "fail" if outcome.verdict is CheckVerdict.MEASURED else "notApplicable",'
)

with open("src/bernstein/cli/commands/governance_cmd.py", "w") as f:
    f.write(content)
