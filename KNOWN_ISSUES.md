# Known Issues and Limitations

This document lists what the grader and harness **cannot** catch. Following the principle
that "known defects are baseline counterexamples for meta-evaluation," each issue is
documented so it can be used to test the evaluation system itself.

## Grader Limitations

### 1. Constraint satisfaction ≠ schedule quality

The grader verifies hard constraints (no double-booking, valid days, work hours, etc.)
but says nothing about whether a schedule is *good*. Two schedules can both pass every
hard rule and differ wildly in quality — one might be thoughtful with buffer time and
sensible grouping, the other technically valid but practically unusable.

**What this means:** A `hard_pass_rate` of 1.0 does not mean the agent is good. It means
the agent doesn't break rules. Qualitative judgment (L2) is needed for the rest.

### 2. No soft-preference gradation

`preference_score` is binary per meeting: a meeting either starts before its
`prefer_before` time or it doesn't. There's no partial credit for "close" (starting at
10:01 when the preference was 10:00) vs "far" (starting at 15:00).

**What this means:** An agent that misses a preference by one minute scores the same as
one that ignores it entirely.

### 3. No attendee workload fairness

The grader checks that no attendee is double-booked, but doesn't check whether one
attendee has 6 meetings in a day while another has 1. A schedule that crams everything
into one person's Monday and leaves everyone else idle still passes.

**What this means:** Fairness across attendees is not measured. This is a qualitative
dimension for the L2 judge.

### 4. No temporal distribution check

The grader doesn't check whether meetings are sensibly distributed across the week.
An agent could schedule everything on Monday and Tuesday and leave Wednesday through
Friday empty, and it would pass every hard constraint.

**What this means:** "All meetings on two days" and "evenly spread across five days" score
identically. This is a quality dimension the grader can't see.

### 5. `--repeats` summary silently skips errored cases

When using `--repeats N`, the min/mean/max summary at the end only includes cases that
didn't error. If Gemini rate-limits (429) most cases in runs 2 and 3, the summary
quietly ignores them and reports an average that looks clean but is based on partial
data.

**What this means:** The "across all runs" block can be misleading. Check the
`errors:` count in each run before trusting the summary.

### 6. No tracing / observability

Every run saves a JSON report to `artifacts/runs/`, but there is no integration with
Langfuse, LangSmith, or any tracing tool. You can't browse runs in a UI, filter by
model/prompt version, or see token usage and latency over time.

**What this means:** Debugging requires reading raw JSON files by hand. There's no
searchable, browsable trace store.

### 7. No human evaluation workflow

The grader is fully deterministic. There is no built-in way to:
- Get 2+ humans to independently label runs as good/bad
- Measure agreement (Cohen's kappa)
- Compare the LLM judge against human consensus using precision/recall
- Document disagreements for adjudication

**What this means:** The LLM judge (`judge.py`) exists but hasn't been calibrated against
human labels. Its `good`/`bad` labels are unvalidated.

### 8. No A/B testing support

There is no built-in way to:
- Run two prompts on the same scenarios and compare min/mean/max
- Run two models on the same scenarios and compare
- Track metric deltas across prompt/model versions over time

**What this means:** Comparing prompt v1 vs prompt v2 requires manually running each and
comparing JSON files by hand. Loggy (import tool) partially addresses this.

### 9. Gemini free-tier rate limits

The Gemini free tier caps requests per minute and per day. Running `--repeats 3` or
running the benchmark multiple times in quick succession will hit 429 errors.

**What this means:** Runs need to be spaced out (5+ minutes between runs). The harness
does not throttle or retry on 429 — it just errors and moves on.

---

## How these map to the teammate's project

| Issue | Teammate's approach |
|---|---|
| Constraint ≠ quality | Explicitly documented: "do not interpret as validated agent quality" |
| No tracing | Langfuse integration, every benchmark item becomes a trace |
| No human eval | Meta-evaluation workflow with independent reviewer exports |
| Known defects | Documented as baseline counterexamples for meta-evaluation |
| No A/B testing | Loggy for comparing runs |
| CI | GitHub Actions runs tests + fixture benchmark |

---

## What's being done

- [ ] Meta-evaluation workflow (human labels → judge precision/recall)
- [ ] Langfuse tracing integration
- [ ] A/B testing via Loggy or built-in compare-runs
- [ ] Fix `--repeats` summary to warn about errors
- [ ] Add soft-preference gradation (partial credit)
- [ ] Add attendee workload fairness metric
- [ ] Add temporal distribution metric
