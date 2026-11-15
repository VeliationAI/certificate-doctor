from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from certificate_doctor.engine import diagnose
from certificate_doctor.report import to_json, to_markdown, write_reports

app = typer.Typer(
    name="certificate-doctor",
    help="Certificate Doctor — forensic screening for certificate/marksheet forgery (0–100).",
    add_completion=False,
)
console = Console()


@app.command("scan")
def scan_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Certificate image or PDF"),
    json_out: bool = typer.Option(False, "--json", help="Print JSON instead of rich summary"),
    markdown: bool = typer.Option(False, "--markdown", help="Print markdown report"),
    export: Optional[Path] = typer.Option(None, "--export", help="Directory for reports + heatmap"),
) -> None:
    """Run all five forensic checks and print a Certificate Doctor score."""
    out_dir = export or Path(".")
    result = diagnose(path, out_dir=out_dir if export else None)

    if export:
        md_path, json_path = write_reports(result, export)
        console.print(f"[green]Wrote[/green] {md_path}")
        console.print(f"[green]Wrote[/green] {json_path}")
        if result.overlay_path:
            console.print(f"[green]Overlay[/green] {result.overlay_path}")
            console.print(f"[green]Heatmap[/green] {result.heatmap_path}")

    if json_out:
        console.print_json(to_json(result))
        return

    if markdown:
        console.print(to_markdown(result))
        return

    color = (
        "green"
        if result.overall_score >= 75
        else "yellow"
        if result.overall_score >= 50
        else "red"
    )
    console.print(
        Panel.fit(
            f"[bold]{result.overall_score:.0f}/100[/bold]  {result.verdict}\n"
            f"{result.file_name} · {result.width}×{result.height}",
            title="Certificate Doctor",
            border_style=color,
        )
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Weight", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Points", justify="right")
    table.add_column("Summary")
    labels = {
        "ela": "ELA",
        "text_font": "Text/font",
        "metadata": "Metadata",
        "copy_move": "Copy-move",
        "logic": "Logic",
    }
    for c in result.checks:
        table.add_row(
            labels.get(c.name, c.name),
            str(c.weight),
            f"{c.score:.0f}",
            f"{c.weighted_score:.1f}",
            c.summary,
        )
    console.print(table)

    if result.top_issues:
        console.print("\n[bold]Findings[/bold]")
        for i, issue in enumerate(result.top_issues, 1):
            console.print(f"  {i}. [{issue.severity}] {issue.title}")
            console.print(f"     {issue.detail}")


@app.callback()
def main() -> None:
    """Certificate Doctor CLI."""


if __name__ == "__main__":
    app()
