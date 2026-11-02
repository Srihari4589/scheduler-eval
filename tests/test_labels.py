"""Tests for the shared label exporter and the inter-rater kappa script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


export_labels = _load("export_labels")
inter_rater = _load("inter_rater")


def _run(report: dict) -> dict:
    return {"cases": [{"case_id": "c1", "error": None, "report": report}]}


def test_no_correction_is_na_for_implicit():
    label, _ = export_labels.implicit_label({"hard_pass": 1.0})
    assert label == "na"


def test_unexercised_correction_is_na_not_pass():
    report = {"regression_score": 1.0, "added_meeting_present": 1.0, "correction_exercised": 0.0}
    assert export_labels.implicit_label(report)[0] == "na"


def test_regression_fails_implicit():
    report = {"regression_score": 0.0, "added_meeting_present": 1.0, "correction_exercised": 1.0}
    label, note = export_labels.implicit_label(report)
    assert label == "fail" and "broke earlier" in note


def test_ignored_correction_fails_implicit():
    report = {"regression_score": 1.0, "added_meeting_present": 0.0, "correction_exercised": 1.0}
    assert export_labels.implicit_label(report)[0] == "fail"


def test_clean_correction_passes_implicit():
    report = {"regression_score": 1.0, "attendee_moved_off_day": 1.0, "correction_exercised": 1.0}
    assert export_labels.implicit_label(report)[0] == "pass"


def test_build_rows_has_quant_implicit_and_human():
    run = _run({"hard_pass": 0.0, "hard_violations": ["x"], "judge_good": True})
    rows = export_labels.build_rows(run, "r1", "ann", {"c1": "bad", "ghost": "good"})
    dims = {(r["rater"], r["dimension"], r["label"]) for r in rows}
    assert ("grader", "quant", "fail") in dims
    assert ("grader", "implicit", "na") in dims
    assert ("llm_judge", "qual", "pass") in dims
    assert ("ann", "overall", "fail") in dims
    assert not any(r["case_id"] == "ghost" for r in rows)


def test_human_labels_require_rater():
    with pytest.raises(SystemExit):
        export_labels.build_rows(_run({"hard_pass": 1.0}), "r1", None, {"c1": "good"})


def test_errored_cases_are_skipped():
    run = {"cases": [{"case_id": "c1", "error": "boom", "report": {}}]}
    assert export_labels.build_rows(run, "r1", None, None) == []


def test_kappa_perfect_and_chance():
    assert inter_rater.cohens_kappa(["pass", "fail"] * 5, ["pass", "fail"] * 5) == pytest.approx(1.0)
    assert inter_rater.cohens_kappa(["pass", "fail"] * 5, ["fail", "pass"] * 5) == pytest.approx(-1.0)


def test_kappa_undefined_when_one_class():
    assert inter_rater.cohens_kappa(["pass"] * 4, ["pass"] * 4) is None


def _row(rater, case, label, source="human", dim="overall"):
    return {"task": "scheduler", "case_id": case, "rater": rater, "dimension": dim,
            "label": label, "source": source}


def test_pairwise_ignores_machines_and_na():
    rows = [
        _row("a", "c1", "pass"), _row("b", "c1", "pass"),
        _row("a", "c2", "fail"), _row("b", "c2", "pass"),
        _row("a", "c3", "na"), _row("b", "c3", "pass"),
        _row("grader", "c1", "pass", source="grader"),
    ]
    (res,) = inter_rater.pairwise(rows, "overall")
    assert res["raters"] == ("a", "b") and res["n"] == 2 and res["raw_agreement"] == 0.5


def test_review_tool_keys_round_trip(tmp_path, monkeypatch):
    """Labels made in the review page ("<run_id>/<case_id>") must reach the exported rows."""
    import json

    review_tool = _load("review_tool")
    run = {"provider": "p", "timestamp": "t", "cases": [
        {"case_id": "c1", "description": "d", "report": {"hard_pass": 1.0},
         "raw_schedules": [{"assignments": []}]}]}
    page = review_tool.build_review_html([("run_a", run), ("run_b", run)])
    assert "run_a/c1" in page and "run_b/c1" in page

    runs = tmp_path / "runs"
    runs.mkdir()
    for rid in ("run_a", "run_b"):
        (runs / f"{rid}.json").write_text(json.dumps(run))
    human = tmp_path / "h.json"
    human.write_text(json.dumps({"run_a/c1": "good", "run_b/c1": "bad"}))
    monkeypatch.setattr(export_labels, "RUNS_DIR", runs)
    monkeypatch.setattr(export_labels, "LABELS_DIR", tmp_path / "labels")
    monkeypatch.setattr("sys.argv", ["x", "--rater", "ann", "--human", str(human)])
    export_labels.main()
    rows = []
    for f in (tmp_path / "labels").glob("*.ann.jsonl"):
        rows += [json.loads(line) for line in f.read_text().splitlines()]
    human_rows = {(r["run_id"], r["label"]) for r in rows if r["source"] == "human"}
    assert human_rows == {("run_a", "pass"), ("run_b", "fail")}
