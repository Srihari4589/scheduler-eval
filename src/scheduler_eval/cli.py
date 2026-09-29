from __future__ import annotations

from pathlib import Path

import typer

from .agent import FixtureProvider, GeminiProvider
from .runner import run_all

app = typer.Typer(add_completion=False)

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios.jsonl"


@app.command()
def benchmark(
    provider: str = typer.Option("fixture", help="fixture | gemini"),
    model: str = typer.Option("gemini-2.0-flash", help="Model name, if provider=gemini"),
    scenarios: Path = typer.Option(DEFAULT_SCENARIOS, help="Path to scenarios .jsonl"),
    user_mode: str = typer.Option("scripted", help="scripted | interactive"),
    repeats: int = typer.Option(1, min=1, help="Run the whole benchmark N times to see variance"),
):
    """Run every scenario through the chosen provider and print a summary."""
    if provider == "fixture":
        p = FixtureProvider()
    elif provider == "gemini":
        p = GeminiProvider(model=model)
    else:
        raise typer.BadParameter(f"Unknown provider: {provider}")

    all_summaries = []
    for i in range(repeats):
        result = run_all(p, scenarios, provider_label=f"{provider}:{model}", user_mode=user_mode)
        all_summaries.append(result["summary"])

        if repeats > 1:
            typer.echo(f"\n=== run {i + 1}/{repeats} ===")
        typer.echo(f"report: {result['_report_path']}")
        typer.echo(f"cases: {result['num_cases']}  errors: {result['errors']}")
        for key, value in result["summary"].items():
            if value is not None:
                typer.echo(f"{key}: {value:.4f}")

        for c in result["cases"]:
            if c["error"]:
                typer.echo(f"\n[{c['case_id']}] ERROR: {c['error'].splitlines()[0]}")
            elif c["report"].get("hard_violations"):
                typer.echo(f"\n[{c['case_id']}] hard violations:")
                for v in c["report"]["hard_violations"]:
                    typer.echo(f"  - {v}")

    if repeats > 1:
        typer.echo("\n=== across all runs (min / mean / max) ===")
        keys = [k for k in all_summaries[0] if any(s.get(k) is not None for s in all_summaries)]
        for k in keys:
            vals = [s[k] for s in all_summaries if s.get(k) is not None]
            typer.echo(f"{k}: {min(vals):.4f} / {sum(vals) / len(vals):.4f} / {max(vals):.4f}")


if __name__ == "__main__":
    app()
