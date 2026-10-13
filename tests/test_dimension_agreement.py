"""Tests for the per-dimension machine-vs-human agreement report."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("dimension_agreement", SCRIPTS / "dimension_agreement.py")
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)


def row(case, rater, dim, label, source):
    return {"task": "scheduler", "case_id": case, "rater": rater, "dimension": dim,
            "label": label, "source": source}


def test_confusion_treats_fail_as_positive():
    machine = {("t", "a"): "fail", ("t", "b"): "fail", ("t", "c"): "pass", ("t", "d"): "pass"}
    human = {("t", "a"): "fail", ("t", "b"): "pass", ("t", "c"): "fail", ("t", "d"): "pass"}
    c = da.confusion(machine, human)
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (1, 1, 1, 1)
    assert c["precision"] == 0.5 and c["recall"] == 0.5


def test_majority_vote_and_ties():
    rows = [
        row("a", "h1", "overall", "fail", "human"), row("a", "h2", "overall", "fail", "human"),
        row("a", "h3", "overall", "pass", "human"),
        row("b", "h1", "overall", "fail", "human"), row("b", "h2", "overall", "pass", "human"),
    ]
    consensus, ties = da.human_consensus(rows, "overall")
    assert consensus == {("scheduler", "a"): "fail"}
    assert ties == 1


def test_machine_overall_is_fail_if_any_dimension_fails_and_na_is_skipped():
    rows = [
        row("a", "grader", "quant", "pass", "grader"), row("a", "grader", "implicit", "fail", "grader"),
        row("b", "grader", "quant", "pass", "grader"), row("b", "grader", "implicit", "na", "grader"),
    ]
    m = da.machine_labels(rows, "overall")["grader"]
    assert m == {("scheduler", "a"): "fail", ("scheduler", "b"): "pass"}


def test_report_per_dimension_catches_a_weak_dimension():
    # Grader is right on quant but misses every human-flagged implicit failure.
    rows = []
    for case in "abcd":
        rows += [row(case, "grader", "quant", "fail", "grader"), row(case, "h1", "quant", "fail", "human")]
        rows += [row(case, "grader", "implicit", "pass", "grader"), row(case, "h1", "implicit", "fail", "human")]
    res = {(r["dimension"], r["rater"]): r for r in da.report(rows, min_n=2)}
    assert res[("quant", "grader")]["recall"] == 1.0
    assert res[("implicit", "grader")]["recall"] == 0.0
    assert res[("implicit", "grader")]["precision"] is None


def test_small_samples_are_flagged():
    rows = [row("a", "grader", "quant", "fail", "grader"), row("a", "h1", "quant", "fail", "human")]
    assert da.report(rows, min_n=20)[0]["small"] is True
