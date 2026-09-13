import re

with open("src/bernstein/cli/commands/governance_cmd.py", "r") as f:
    content = f.read()

# Fix indentation and variables
old_str = '''    exit_code = 0
    if required:
        has_failed = False
        has_unmeasurable = False
        for outcome in outcomes:
            if outcome.check_id in required:
                if outcome.verdict is CheckVerdict.MEASURED and not outcome.passed:
                    has_failed = True
                elif outcome.verdict is CheckVerdict.NOT_MEASURABLE:
                    has_unmeasurable = True

        if strict and has_unmeasurable:
            exit_code = 2
        elif has_failed:
            exit_code = 1

    if quiet:
        raise SystemExit(exit_code)

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "schema_version": 1,
                    "area": CMP_AREA,
                    "profile": profile.lower() if profile else None,
                    "checks_run": len(outcomes),
                    "checks": [outcome.to_dict() | {"required": outcome.check_id in required} for outcome in outcomes],
                    "counts": counts,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(exit_code)

    if output_format == "sarif":
        click.echo(
            json.dumps(
                {
                    "version": "2.1.0",
                    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                    "runs": [
                        {
                            "tool": {
                                "driver": {
                                    "name": "bernstein",
                                }
                            },
                            "results": [
                                {
                                    "ruleId": outcome.check_id,
                                    "kind": outcome.verdict.value,
                                    "message": {"text": outcome.summary},
                                }
                                for outcome in outcomes
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(exit_code)'''

content = content.replace(old_str, old_str)

# Write it out
with open("src/bernstein/cli/commands/governance_cmd.py", "w") as f:
    f.write(content)
