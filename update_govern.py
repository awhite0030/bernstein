import re

with open("src/bernstein/cli/commands/governance_cmd.py", "r") as f:
    content = f.read()

content = content.replace(
    '@click.option("--json-output", "as_json", is_flag=True, help="Print the report as JSON and nothing else.")',
    """@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
    help="Emit the report as text (default), JSON, or SARIF.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit 2 if any required check is not_measurable.",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Print nothing; the exit code is the whole answer.",
)"""
)

content = content.replace(
    '    profile: str | None,\n    list_only: bool,\n    as_json: bool,\n) -> None:',
    '    profile: str | None,\n    list_only: bool,\n    output_format: str,\n    strict: bool,\n    quiet: bool,\n) -> None:'
)

content = content.replace(
    '    if list_only:\n        _print_audit_catalogue([specs[cid] for cid in selected], required, as_json=as_json)\n        return',
    '    if list_only:\n        if not quiet:\n            _print_audit_catalogue([specs[cid] for cid in selected], required, as_json=(output_format == "json"))\n        return'
)

body = '''    outcomes = run_compliance_checks(workdir, only=only, skip=skip)
    counts = count_by_outcome(outcomes)

    exit_code = 0
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
                                    "kind": "pass" if outcome.passed else "fail" if outcome.verdict is CheckVerdict.MEASURED else "notApplicable",
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

old_body = '''    outcomes = run_compliance_checks(workdir, only=only, skip=skip)
    counts = count_by_outcome(outcomes)

    if as_json:
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
        return'''

content = content.replace(old_body, body)

content = content.replace(
    '            "(marked *; the profile selects ids and states nothing about the result)"\n        )',
    '            "(marked *; the profile selects ids and states nothing about the result)"\n        )\n\n    raise SystemExit(exit_code)'
)

with open("src/bernstein/cli/commands/governance_cmd.py", "w") as f:
    f.write(content)
