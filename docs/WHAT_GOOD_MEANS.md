# What "good" means for the scheduler agent

*Draft v1 for team review. This is the shared starting point; the three repos
(scheduler, CSV analysis, transcription) should use the same three dimensions and
the same label format, so results can be compared.*

A run is **good** only if it passes all three dimensions below. A run can fail one
dimension and pass the others, so each is labeled separately. Do not average them.

## 1. Quantitative: checkable by code

The final schedule satisfies every hard rule, and nothing is missing.

- **Pass:** no double-booked shared attendee, every meeting is placed exactly once,
  fixed days / `not_before` / deadlines / blocked times are respected.
- **Fail:** any hard violation, or any meeting missing.
- **Source:** `grader.py` (`hard_pass`). No human judgment needed.

## 2. Qualitative: needs a person (or a judge calibrated to people)

The schedule is valid *and* something a real person would want to follow.

- **Pass:** reasonable buffer between meetings, related meetings grouped, demanding
  meetings not at the worst times, no single attendee stuck with all the bad slots,
  soft preferences (e.g. "before 11am") honored where possible.
- **Fail:** technically valid but back-to-back all day, scattered, or ignores
  preferences with no reason.
- **Source:** human labelers first; the LLM judge (`judge.py`) is only trusted after
  its precision/recall against human labels is reported.
- **Where raters will disagree:** how much buffer is "enough", whether grouping beats
  spreading. Disagreements are data. Record them, don't hide them.

## 3. Implicit: inferred from behavior around the correction

When the user pushes back mid-task, the agent adapts without breaking earlier work.

- **Pass:** the correction is applied (meeting added/removed, attendee moved, time
  blocked) **and** constraints that held before still hold (`regression_score = 1.0`).
- **Fail:** correction ignored, or the fix broke something that was already right.
- **Not scoreable:** if the first schedule never conflicted with the correction
  (`correction_exercised = 0`), the correction forced no change and a pass means
  little. Label these `n/a`, not `pass`.
- **Source:** grader metrics, plus a human check that the compliance matches intent.

## Overall label (what human raters give per run)

`pass` if all scoreable dimensions pass, else `fail`. Raters also write a one-line
note on *why*. Notes matter more than the label for finding failure types.

## Shared label format (all three repos)

One JSON object per line, one line per (run, rater, dimension):

```json
{"task": "scheduler", "run_id": "20261012T200000Z", "case_id": "baseline_week",
 "rater": "srihari", "dimension": "overall", "label": "fail",
 "note": "back-to-back Mon, no lunch gap", "source": "human"}
```

| field | values |
|---|---|
| `task` | `scheduler` / `csv_analysis` / `transcription` |
| `dimension` | `quant` / `qual` / `implicit` / `overall` |
| `label` | `pass` / `fail` / `na` |
| `source` | `human` / `grader` / `judge` |

Tools: `scripts/export_labels.py` writes this format; `scripts/inter_rater.py` reports
Cohen's kappa between raters; `scripts/measure_agreement.py` reports judge precision
and recall against human labels.

## Open questions for the team and mentors

1. Is "overall = all dimensions pass" too strict? Should qual weigh more?
2. How many runs per rater is enough for a kappa worth reporting (we propose 15-20)?
3. Should `na` implicit cases be dropped from the overall label or counted as pass?
