# scheduler-eval

A small scheduling agent, built to be evaluated across three kinds of signal:
**quantitative** (checkable by code), **qualitative** (needs human/LLM judgment),
and **implicit** (inferred from behavior, like corrections and retries).

This exists to *practice evaluation*, not to be a great scheduler. See
`docs/` (or ask the person who gave you this) for the full project context.

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
  cli.py                      `scheduler-eval` command
tests/                        unit + integration tests for the grader/harness itself
artifacts/runs/               saved JSON reports, one per run
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
scheduler-eval --provider gemini --model gemini-2.0-flash
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
Prints each run, then min / mean / max of every metric. If scores never move, the
scenarios are probably too easy.

## Reading the scores

| Metric | Meaning |
|---|---|
| `hard_pass_rate` | fraction of cases with zero hard-constraint violations in the FINAL schedule |
| `avg_preference_score` | how often soft preferences (like "prefer_before") were honored |
| `avg_regression_score` | for corrected cases: did the ORIGINAL constraints still hold after the correction? (0 = the agent broke something it had already gotten right) |
| `avg_added_meeting_present` / `avg_removed_meeting_absent` / etc. | did the agent actually comply with the specific correction given |
| `avg_correction_exercised` | did the FIRST schedule already conflict with the correction? If a scenario shows 0 here, the correction never forced a change and a pass means little |

`hard_violations` and `regression_violations` in the per-case report are
human-readable strings - read these when you're looking at traces by hand.

## Getting a free Gemini key

1. Go to https://aistudio.google.com/apikey (a Google account is enough, no credit card).
2. Create a key, then `export GEMINI_API_KEY=...` in your shell.

## What this repo does NOT yet cover

This is Level 1 (quantitative unit tests) from Hamel's eval workflow
(https://hamel.dev/blog/posts/evals/index.html). Still missing, on purpose, for now:

- **Tracing** - hook this up to Langfuse (or similar) so every run is a browsable trace.
- **Qualitative judging** - human or LLM review of *schedule quality*, not just
  constraint satisfaction (two schedules can both pass `hard_pass` and differ wildly
  in how good they are).
- **Human labeling + agreement** - get 2+ people to independently label real runs as
  good/bad, and report how often they agree (e.g. Cohen's kappa).
- **LLM-judge-vs-human comparison** - if you add an LLM judge, check its precision/
  recall against the human labels, not raw agreement (Hamel is explicit about this).
- **Variance / reliability analysis** - run the same scenario N times per model/prompt
  and see how much the scores move around.
- **A/B testing** - compare `planner_v1.txt` against a second prompt version, or one
  model against another, properly (fixed test set, multiple repeats).

## Adding a new scenario

Add a line to `data/scenarios.jsonl` following the `ScenarioCase` shape in
`schemas.py`. Set `"correction": null` for a no-correction case, or fill in a
`Correction` object (only the fields relevant to your scenario need to be set -
`adds_meeting`, `removes_meeting_id`, `adds_blocked_time`, or
`reassign_attendee_unavailable`). Then add a `(turn-1 schedule, final schedule)` entry for it in
`tests/test_runner.py`'s `PERFECT` dict. The tests will fail until you do, and they
also check that (a) turn 1 is valid, (b) the correction really changes something in
turn 1, and (c) an agent that ignores the correction fails the scenario.
