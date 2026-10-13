# scheduler-eval

A small scheduling agent, built to be evaluated across three kinds of signal:
**quantitative** (checkable by code), **qualitative** (needs human/LLM judgment),
and **implicit** (inferred from behavior, like corrections and retries).

This exists to *practice evaluation*, not to be a great scheduler. See
`docs/WHAT_GOOD_MEANS.md` for the shared definition of "good" and the team label format.

## The task

The agent is given a list of meetings to place into a Mon-Fri, 09:00-17:00 week,
subject to hard rules (no double-booking a shared attendee, respect fixed days,
earliest-start times, deadlines, blocked times) and soft preferences (e.g. "ideally
before 11am"). For some scenarios, a mid-task correction arrives after the agent's
first attempt ("actually add this meeting", "Sam can't do Tuesday anymore"), and the
agent has to revise its schedule without breaking the constraints it already
satisfied.

That correction step is the whole point: a one-shot agent can't produce retries,
corrections, or "did it forget what I told it earlier" failures. This one can.

## Why this design (the four checks)

1. **Checkable by code** - hard constraints are unambiguous (a double-booking either
   exists or it doesn't), so `grader.py` can score them with plain arithmetic, no AI.
2. **Room for real human disagreement** - many schedules satisfy every hard rule, but
   people will differ on which one is actually *good* (energy, grouping, buffer time).
   That's the qualitative dimension, and it isn't a formality here.
3. **Natural implicit signals** - the mid-task correction is a real "user pushes back"
   moment, not a bolted-on feature.
4. **Cheap variety of distinct failures** - hard-constraint violation, "forgot an
   earlier rule while fixing a new one" (regression), ignoring the correction
   entirely, and a technically-valid-but-bad schedule are all different failure
   *types*, not just "right vs wrong."

## Project layout

```
prompts/planner_v1.txt        the agent's system prompt
data/scenarios.jsonl          test scenarios (some with a mid-task correction)
src/scheduler_eval/
  schemas.py                  plain data models (no AI)
  agent.py                    the actual agent: GeminiProvider + FixtureProvider
  grader.py                   plain-Python scoring (no AI)
  runner.py                   runs scenarios end-to-end, saves a report
  judge.py                    LLM judge for qualitative schedule quality
  judge_eval.py               tests the judge against schedules with injected, known defects
  stats.py                    bootstrap CIs (per repeat and per scenario) + per-dimension strict gating
  tracing.py                  one JSONL trace per run (every step, timing, grader output)
  langfuse_export.py          optional: push a trace to Langfuse (dry-run works without it)
  cli.py                      `scheduler-eval` command
scripts/
  review_tool.py              HTML page for human good/bad labeling
  export_labels.py            write labels in the team's shared JSONL format
  inter_rater.py              Cohen's kappa between human raters
  measure_agreement.py        LLM judge precision/recall vs human labels
  dimension_agreement.py      grader/judge vs human consensus, per dimension (confusion matrix)
  evaluate_judge.py           judge vs injected known defects (fast check, no humans)
  import_loggy.py             import runs from Loggy
  generate_report.py          build the PDF report
docs/WHAT_GOOD_MEANS.md       shared definition of "good" (quant / qual / implicit)
tests/                        unit + integration tests for the grader/harness itself
artifacts/runs/               saved JSON reports, one per run
artifacts/traces/             one JSONL trace per run (git-ignored)
artifacts/labels/             exported labels (shared format)
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                             # sanity-check the harness itself, no API key needed
```

## Running it

**Free, no API key** (tests the harness with a deliberately naive, mostly-wrong
placement - useful for confirming the grader correctly flags violations):
```bash
scheduler-eval --provider fixture
```

**With a real model** (Google Gemini, free tier - see "Getting a Gemini key" below):
```bash
pip install -e ".[gemini]"
export GEMINI_API_KEY=your_key     # Windows: set GEMINI_API_KEY=your_key
scheduler-eval --provider gemini --model gemini-3.5-flash-lite
```

**Interactive mode** - type the mid-task correction yourself instead of using the
pre-scripted one:
```bash
scheduler-eval --provider gemini --user-mode interactive
```

Each run prints a summary and saves the full report (every case, every schedule the
model produced, every violation) to `artifacts/runs/<timestamp>.json`.

## Scenarios

| id | correction | what it stresses |
|---|---|---|
| `baseline_week` | none | basic mix of constraints |
| `add_meeting_midtask` | adds a meeting | fitting a new item in |
| `attendee_unavailable_midtask` | Sam unavailable Tue | turn 1 is forced onto Tue, so the agent must really move things |
| `remove_meeting_midtask` | cancels a meeting | dropping cleanly without disturbing the rest |
| `blocked_time_midtask` | blocks Wed 09:00-10:30 | tight 90-minute window, exactly enough room |
| `dense_week_add_big_meeting` | adds a 2-hour meeting | crowded week, daily lunch blocked |

## Repeated runs (variance)

```bash
scheduler-eval --provider gemini --model gemini-3.5-flash-lite --repeats 5
```
Prints each run, then min / mean / max of every metric plus a 95% bootstrap
confidence interval of the mean (`CI [low, high]`) and `n=` showing how many of the
repeats produced a value. That first CI only reflects run-to-run noise on this fixed
scenario set, and with fewer than 5 repeats it is rough (the CLI says so).

A second block, "scenario-level 95% CI", resamples the scenarios themselves and then the
repeats inside each one, so it also reflects that we only tried a handful of scenarios.
It prints for every run, even with `--repeats 1`. Expect it to be wide; a metric that
exists in fewer than 3 scenarios is flagged because its interval means nothing. If scores
never move, the scenarios are probably too easy.

## Reading the scores

| Metric | Meaning |
|---|---|
| `hard_pass_rate` | fraction of cases with zero hard-constraint violations in the FINAL schedule |
| `avg_preference_score` | how often soft preferences (like "prefer_before") were honored |
| `avg_regression_score` | for corrected cases: did the ORIGINAL constraints still hold after the correction? (0 = the agent broke something it had already gotten right) |
| `avg_added_meeting_present` / `avg_removed_meeting_absent` / etc. | did the agent actually comply with the specific correction given |
| `avg_correction_exercised` | did the FIRST schedule already conflict with the correction? If a scenario shows 0 here, the correction never forced a change and a pass means little |

**Averages hide failures, so read the strict numbers.** Every case report has a
`gate`: a case is a *strict pass* only if every dimension (hard rules, regression,
each correction check) is 1.0, and the failing dimensions are named. The run prints
a per-dimension pass rate, the weakest dimension, and `strict_pass_rate`. A run with
`hard_pass_rate` 0.0 can still average 0.6 across metrics; the strict rate will not.
If `correction_exercised` is 0 for a case, the correction forced no change and its
pass is flagged rather than trusted.

`hard_violations` and `regression_violations` in the per-case report are
human-readable strings - read these when you're looking at traces by hand.

## Traces

Every run writes `artifacts/traces/<run_id>.jsonl`, one line per step:
`agent_turn_1`, `user_correction`, `agent_turn_2`, `grade`. Each line has the case id,
timestamps, duration, the schedule the agent returned, and the grader's report.
```bash
jq -c 'select(.span=="grade") | {case_id, hard: .report.hard_pass}' artifacts/traces/<run_id>.jsonl
```
These are plain local files. To browse them in Langfuse, `pip install -e ".[langfuse]"`, set the
Langfuse env vars, and run `python -m scheduler_eval.langfuse_export artifacts/traces/<run>.jsonl`
(add `--dry-run` to preview). Verified on 2026-10-12 against Langfuse Cloud (US) with Langfuse SDK 4.17: all 6 fixture traces and their scores appeared.
The `run_id` matches the report file in `artifacts/runs/`.

## Testing the judge itself

The LLM judge can be wrong too. `evaluate_judge.py` builds well-spaced valid schedules,
injects one known defect each (missing meeting, double-booking, outside work hours,
blocked time, everything back-to-back, everything crammed late), and measures whether
the judge catches them:
```bash
python scripts/evaluate_judge.py --judge stubborn   # negative control: recall must be 0
python scripts/evaluate_judge.py --judge gemini     # the real judge
```
It reports precision and recall for catching bad schedules, the false-positive rate
on good ones, and recall per defect type. The judge is not shown the grader's verdict
unless you pass `--show-grader`. The defects are synthetic and blatant, so this is a
fast sanity check, **not** a substitute for real human labels.

## Getting a free Gemini key

1. Go to https://aistudio.google.com/apikey (a Google account is enough, no credit card).
2. Create a key, then `export GEMINI_API_KEY=...` in your shell.

## Judging and human labeling

```bash
scheduler-eval --provider gemini --judge          # LLM judge on the last repeat
python scripts/review_tool.py                     # builds artifacts/review.html
# label cases in the browser, export human_labels.json
python scripts/export_labels.py --rater <yourname> --human human_labels.json
python scripts/inter_rater.py artifacts/labels/*.jsonl      # kappa between raters
python scripts/measure_agreement.py human_labels.json       # judge vs human P/R
```

The label format and what each dimension means are in `docs/WHAT_GOOD_MEANS.md`.

## What this repo does NOT yet cover

This covers Level 1 (unit tests) and the tooling for Level 2 (judge + human labels)
from Hamel's eval workflow (https://hamel.dev/blog/posts/evals/index.html). Still
missing:

- **Real human labels from 2+ people.** The tooling exists; the labeled data and
  the agreement numbers do not yet. This is the main open deliverable.
- **Hosted tracing.** Traces are local JSONL; the optional Langfuse export was verified once on the fixture benchmark only (SDK 4.17), not on real Gemini runs.
- **A/B testing** - compare `planner_v1.txt` against a second prompt version, or one
  model against another, properly (fixed test set, multiple repeats).
- **Judge vs humans.** `evaluate_judge.py` only shows the judge catches planted
  defects; whether it agrees with people is still unmeasured.

See `KNOWN_ISSUES.md` for other limitations.

## Adding a new scenario

Add a line to `data/scenarios.jsonl` following the `ScenarioCase` shape in
`schemas.py`. Set `"correction": null` for a no-correction case, or fill in a
`Correction` object (only the fields relevant to your scenario need to be set -
`adds_meeting`, `removes_meeting_id`, `adds_blocked_time`, or
`reassign_attendee_unavailable`). Then add a `(turn-1 schedule, final schedule)` entry for it in
`tests/test_runner.py`'s `PERFECT` dict. The tests will fail until you do, and they
also check that (a) turn 1 is valid, (b) the correction really changes something in
turn 1, and (c) an agent that ignores the correction fails the scenario.
