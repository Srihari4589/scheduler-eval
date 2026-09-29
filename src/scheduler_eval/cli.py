from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

from .agent import FixtureProvider, GeminiProvider
from .judge import GeminiJudge, StubbornJudge
from .runner import run_all, load_scenarios, _apply_correction_to_scenario
from .schemas import ScheduleOutput

app = typer.Typer(add_completion=False)

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios.jsonl"


@app.command()
def benchmark(
    provider: str = typer.Option("fixture", help="fixture | gemini"),
    model: str = typer.Option("gemini-3.5-flash-lite", help="Model name, if provider=gemini"),
    scenarios: Path = typer.Option(DEFAULT_SCENARIOS, help="Path to scenarios .jsonl"),
    user_mode: str = typer.Option("scripted", help="scripted | interactive"),
    repeats: int = typer.Option(1, min=1, help="Run the whole benchmark N times to see variance"),
    judge: str = typer.Option("none", help="none | gemini | stubborn - L2 qualitative evaluation"),
    judge_model: str = typer.Option("gemini-2.5-pro", help="Model name, if judge=gemini"),
):
    """Run every scenario through the chosen provider and print a summary."""
    if provider == "fixture":
        p = FixtureProvider()
    elif provider == "gemini":
        p = GeminiProvider(model=model)
    else:
        raise typer.BadParameter(f"Unknown provider: {provider}")

    all_summaries = []
    all_errors = []
    for i in range(repeats):
        result = run_all(p, scenarios, provider_label=f"{provider}:{model}", user_mode=user_mode)
        all_summaries.append(result["summary"])
        all_errors.append(result["errors"])

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
            # NOTE: a metric can have fewer than `repeats` values if some runs errored
            # out entirely for every case (e.g. rate limits) - always show the count so
            # a clean-looking average isn't mistaken for one backed by all N runs.
            typer.echo(
                f"{k}: {min(vals):.4f} / {sum(vals) / len(vals):.4f} / {max(vals):.4f}"
                f"  (n={len(vals)}/{repeats})"
            )
        if any(e > 0 for e in all_errors):
            typer.echo(
                f"\nWarning: {sum(all_errors)} case-run(s) errored across these {repeats} "
                f"runs (see per-run 'errors:' counts above, e.g. rate limits). The "
                f"min/mean/max above only reflects runs/cases that succeeded."
            )

    if judge != "none":
        if repeats > 1:
            typer.echo(
                f"\nNote: --repeats={repeats} was used, but the judge only evaluates "
                f"the LAST run (run {repeats}/{repeats}), not all repeats."
            )
        typer.echo(f"\n=== L2 Qualitative Judge ({judge}:{judge_model}) ===")
        if judge == "gemini":
            j = GeminiJudge(model=judge_model)
        elif judge == "stubborn":
            j = StubbornJudge()
        else:
            raise typer.BadParameter(f"Unknown judge: {judge}")

        for c in result["cases"]:
            if c["error"]:
                continue
            final_raw = c["raw_schedules"][-1]
            final_schedule = ScheduleOutput.model_validate(final_raw)
            all_cases = load_scenarios(scenarios)
            case = next((x for x in all_cases if x.id == c["case_id"]), None)
            if case is None:
                continue
            final_input, _ = _apply_correction_to_scenario(case.input, case)

            judge_result = j.evaluate(final_input, final_schedule, c["report"])
            c["report"]["judge_good"] = judge_result["good"]
            c["report"]["judge_critique"] = judge_result["critique"]
            c["report"]["judge_scores"] = judge_result["scores"]

            typer.echo(f"\n[{c['case_id']}] judge: {'GOOD' if judge_result['good'] else 'BAD'}")
            typer.echo(f"  critique: {judge_result['critique']}")
            for dim, score in judge_result["scores"].items():
                typer.echo(f"  {dim}: {score:.2f}")

        artifacts_dir = Path(__file__).resolve().parents[2] / "artifacts" / "runs"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        out_path = artifacts_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        result["_judge_path"] = str(out_path)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        typer.echo(f"\njudge report: {out_path}")


if __name__ == "__main__":
    app()
