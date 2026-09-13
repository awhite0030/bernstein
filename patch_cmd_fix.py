import re
import json

with open("src/bernstein/cli/commands/governance_cmd.py", "r") as f:
    content = f.read()

# Replace json-output option with format, strict, and quiet
old_options = '''@click.option("--list", "list_only", is_flag=True, help="Print the registered check ids and exit.")
@click.option("--json-output", "as_json", is_flag=True, help="Print the report as JSON and nothing else.")
def govern_audit_cmd(
    workdir: Path,
    only: tuple[str, ...],
    skip: tuple[str, ...],
    profile: str | None,
    list_only: bool,
    as_json: bool,
) -> None:'''

new_options = '''@click.option("--list", "list_only", is_flag=True, help="Print the registered check ids and exit.")
@click.option(
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
)
def govern_audit_cmd(
    workdir: Path,
    only: tuple[str, ...],
    skip: tuple[str, ...],
    profile: str | None,
    list_only: bool,
    output_format: str,
    strict: bool,
    quiet: bool,
) -> None:'''

content = content.replace(old_options, new_options)

# Update internal _print_audit_catalogue call
old_list = '''    if list_only:
        _print_audit_catalogue([specs[cid] for cid in selected], required, as_json=as_json)
        return'''
new_list = '''    if list_only:
        if not quiet:
            _print_audit_catalogue([specs[cid] for cid in selected], required, as_json=(output_format == "json"))
        return'''

content = content.replace(old_list, new_list)

# Update outcomes logic
old_outcomes = '''    outcomes = run_compliance_checks(workdir, only=only, skip=skip)
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

new_outcomes = '''    outcomes = run_compliance_checks(workdir, only=only, skip=skip)
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

content = content.replace(old_outcomes, new_outcomes)

# Update bottom return to system exit
old_bottom = '''    if profile:
        click.echo("")
        click.echo(
            f"  required by profile {profile.lower()}: "
            f"{len(required & {o.check_id for o in outcomes})} of {total} ids "
            "(marked *; the profile selects ids and states nothing about the result)"
        )'''

new_bottom = '''    if profile:
        click.echo("")
        click.echo(
            f"  required by profile {profile.lower()}: "
            f"{len(required & {o.check_id for o in outcomes})} of {total} ids "
            "(marked *; the profile selects ids and states nothing about the result)"
        )

    raise SystemExit(exit_code)'''
content = content.replace(old_bottom, new_bottom)


with open("src/bernstein/cli/commands/governance_cmd.py", "w") as f:
    f.write(content)
