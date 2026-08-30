from __future__ import annotations

from pathlib import Path

import click
from rich.table import Table

from bernstein.adapters.onboarding import probe_cli
from bernstein.cli.helpers import console


@click.command("onboard")
@click.argument("binary", required=True)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=Path(".bernstein/onboard"),
    help="Directory to write evidence files into.",
)
def adapters_onboard_cmd(binary: str, out_dir: Path) -> None:
    """Probe an installed CLI binary and capture its self-description as evidence.

    Produces content-addressed evidence files without evaluating them.
    """
    console.print(f"Probing binary: [cyan]{binary}[/cyan]")
    evidence = probe_cli(binary, out_dir)

    table = Table(title="Probe Evidence", show_lines=False)
    table.add_column("command", style="white")
    table.add_column("exit", justify="right")
    table.add_column("sha256", style="dim")

    for ev in evidence:
        exit_style = "[green]" if ev.exit_code == 0 else "[red]"
        table.add_row(ev.command, f"{exit_style}{ev.exit_code}[/]", ev.sha256[:12] + "...")

    console.print(table)
    console.print(f"\n[green]Wrote {len(evidence)} evidence files to {out_dir}[/green]")


def register_adapters_onboard(group: click.Group) -> None:
    group.add_command(adapters_onboard_cmd, "onboard")
