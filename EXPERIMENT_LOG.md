# Experiment log

One row per thing tried: what I did, what came out, what it means, what's next.

| Date | What I tried | What happened | Why / what it means | Next step |
|---|---|---|---|---|
| 2026-09-29 | Ran `scheduler-eval --provider fixture` (naive placement, no AI) | hard_pass_rate 0.0, many violations listed | Grader catches real mistakes, so it can fail | Run a real model |
| 2026-09-29 | Ran 3 scenarios on `gemini:gemini-3.5-flash-lite` | 0 errors, every score 1.0 | Too easy to be informative. Read the trace by hand: in `attendee_unavailable_midtask` the first schedule never put anything on Tuesday, so the correction changed nothing | Rebuild that scenario so turn 1 is forced onto Tuesday |
| 2026-09-29 | Forced Sam's meetings onto Tuesday with `fixed_day`, added `_lift_superseded_fixed_day` to the grader, 14 tests | 14 passed. Two more Gemini runs on the 3 scenarios: 0 errors, every score 1.0 again | The fixed-day rule is lifted when a correction supersedes it, so moving off Tuesday is no longer penalised | Add harder scenarios; check the grader can still fail |
| 2026-09-29 | Added negative control (`StubbornProvider` ignores every correction) plus a `correction_exercised` metric | Found: with the old grader, ignoring the correction still gave `hard_pass` 1.0 (the fixed_day rule was lifted, nothing replaced it) | A score can be perfect and measure nothing. Grader now adds a hard violation when an unavailable attendee is still booked that day | Keep the negative control in the test suite |
| 2026-09-29 | Added `remove_meeting_midtask` scenario | Found a second grader bug: the regression check still expected the cancelled meeting, so a correct agent scored `regression_score` 0 | Fixed in `runner.py`; the perfect-provider test now covers it | Run it on a real model |
| 2026-09-29 | Added `blocked_time_midtask` and `dense_week_add_big_meeting`, plus `--repeats N` | Tests only so far (21 passed). NOT yet run on Gemini | Need real runs to see whether the model can fail on the tighter scenarios | Run `scheduler-eval --provider gemini --model gemini-3.5-flash-lite --repeats 5` and record min/mean/max |

## Open questions
- Does `gemini-3.5-flash-lite` ever drop below 1.0 on the 6 scenarios, or are they still too easy?
- Is a second, weaker model available on the free tier, to check the grader separates good from bad?
- What does "a good schedule" mean beyond passing the hard rules? (half-page written definition still to do)

## Findings

- 2026-09-29: On `gemini-3.5-flash-lite`, 6 scenarios, two clean runs (errors: 0) gave identical scores: hard_pass_rate 1.0, avg_preference_score 0.9444, every correction metric 1.0, avg_correction_exercised 1.0.
- The only miss both times was in `dense_week_add_big_meeting`: `qa-triage` (prefer_before 10:00) was placed at exactly 10:00, first on Wed and then on Mon. Repeatable, so not random.
- Guess (untested): the model may read "before 10:00" as "by 10:00". Next test: reword the prompt to say strictly earlier than that time, and see whether the miss goes away.
- The `--repeats 3` run on this date was invalid: Gemini free-tier limit (429) errored most cases in runs 2 and 3, and the min/mean/max summary skipped them. Wait about 5 minutes between runs.
