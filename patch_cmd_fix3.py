with open("src/bernstein/cli/commands/governance_cmd.py", "r") as f:
    content = f.read()

# Ah! The original `_print_audit_catalogue` had an `if as_json:` condition that we replaced, but we left the `raise SystemExit(exit_code)` inside `_print_audit_catalogue`! Let's fix that.

old_catalogue = '''def _print_audit_catalogue(
    specs: list[ComplianceCheckSpec],
    required: frozenset[str],
    *,
    as_json: bool,
) -> None:
    """Print the registered check ids without running any of them."""
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "check_id": spec.check_id,
                        "area": spec.area,
                        "asserts": spec.asserts,
                        "required": spec.check_id in required,
                    }
                    for spec in specs
                ],
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
        raise SystemExit(exit_code)
    for spec in specs:
        marker = "*" if spec.check_id in required else " "
        click.echo(f"  {marker}{spec.check_id}  {spec.area:<12}  {spec.asserts}")'''

new_catalogue = '''def _print_audit_catalogue(
    specs: list[ComplianceCheckSpec],
    required: frozenset[str],
    *,
    as_json: bool,
) -> None:
    """Print the registered check ids without running any of them."""
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "check_id": spec.check_id,
                        "area": spec.area,
                        "asserts": spec.asserts,
                        "required": spec.check_id in required,
                    }
                    for spec in specs
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for spec in specs:
        marker = "*" if spec.check_id in required else " "
        click.echo(f"  {marker}{spec.check_id}  {spec.area:<12}  {spec.asserts}")'''

content = content.replace(old_catalogue, new_catalogue)

with open("src/bernstein/cli/commands/governance_cmd.py", "w") as f:
    f.write(content)
