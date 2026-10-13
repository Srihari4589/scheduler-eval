import json

from scheduler_eval.langfuse_export import case_records, export, load_spans


def _write(tmp_path):
    rows = [
        {"run_id": "r", "case_id": "a", "span": "agent_turn_1", "assignments": [], "duration_s": 0.1},
        {"run_id": "r", "case_id": "a", "span": "grade", "duration_s": 0.0,
         "report": {"hard_pass": 1.0, "preference_score": 0.5, "hard_violations": ["x"]}},
        {"run_id": "r", "case_id": "b", "span": "agent_turn_1", "error": "RuntimeError: 429"},
    ]
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_groups_by_case_and_extracts_numeric_scores(tmp_path):
    spans = load_spans(_write(tmp_path))
    assert set(spans) == {"a", "b"}
    rec = case_records("a", spans["a"])
    assert rec["scores"] == {"hard_pass": 1.0, "preference_score": 0.5}  # list field ignored
    assert rec["error"] is None


def test_errors_are_carried_through(tmp_path):
    spans = load_spans(_write(tmp_path))
    assert case_records("b", spans["b"])["error"] == "RuntimeError: 429"


def test_dry_run_needs_no_langfuse(tmp_path, capsys):
    assert export(_write(tmp_path), dry_run=True) == 2
    assert "[dry-run] a" in capsys.readouterr().out
