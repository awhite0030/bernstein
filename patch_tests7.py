import re

with open("tests/unit/cli/test_govern_audit_cmd.py", "r") as f:
    content = f.read()

# Let's fix the mocking for CheckVerdict since `outcome.verdict is CheckVerdict.MEASURED` checks identity, maybe there's a difference? Actually wait, `required` is frozenset in real implementation.
# In `test_govern_audit_exit_code_one_failed`, we mock `required_check_ids` with `{"CMP-001"}`. This gets passed to `required` parameter... oh wait.
# In `govern_audit_cmd`, `required_check_ids` is called IF `profile` is provided! If `--profile` is not provided, `required` is an empty frozenset.
# Ah! I didn't pass `--profile soc2` in the new tests!

# Let's add `--profile soc2` to the new tests so that `required` is actually populated.

content = content.replace('"--workdir", str(project)])', '"--workdir", str(project), "--profile", "soc2"])')
content = content.replace('"--workdir", str(project), "--strict"])', '"--workdir", str(project), "--profile", "soc2", "--strict"])')
content = content.replace('"--workdir", str(project), "--quiet"])', '"--workdir", str(project), "--profile", "soc2", "--quiet"])')
content = content.replace('"--workdir", str(project), "--format", "sarif"])', '"--workdir", str(project), "--profile", "soc2", "--format", "sarif"])')

with open("tests/unit/cli/test_govern_audit_cmd.py", "w") as f:
    f.write(content)
