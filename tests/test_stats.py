from scheduler_eval.stats import bootstrap_ci, case_gate, per_dimension_summary


def test_bootstrap_is_deterministic_and_brackets_the_mean():
    vals = [0.2, 0.4, 0.6, 0.8, 1.0]
    a = bootstrap_ci(vals)
    assert a == bootstrap_ci(vals)
    lo, mean, hi = a
    assert lo <= mean <= hi
    assert abs(mean - 0.6) < 1e-9
    assert hi - lo > 0.1  # real variance gives a real interval


def test_bootstrap_empty_and_constant():
    assert bootstrap_ci([]) is None
    assert bootstrap_ci([1.0, 1.0, 1.0]) == (1.0, 1.0, 1.0)


def test_one_failed_dimension_cannot_hide_in_an_average():
    report = {"hard_pass": 0.0, "regression_score": 1.0, "added_meeting_present": 1.0,
              "preference_score": 1.0, "correction_exercised": 1.0}
    gate = case_gate(report)
    avg = sum(gate["dimensions"].values()) / len(gate["dimensions"])
    assert avg > 0.6                      # the average still looks fine...
    assert gate["strict_pass"] is False   # ...but the strict verdict does not
    assert gate["failed_dimensions"] == ["hard_pass"]
    assert gate["weakest_dimension"] == "hard_pass"


def test_unexercised_correction_is_flagged():
    gate = case_gate({"hard_pass": 1.0, "attendee_moved_off_unavailable_day": 1.0,
                      "correction_exercised": 0.0})
    assert gate["correction_not_exercised"] is True


def test_per_dimension_summary_names_weakest():
    reports = [
        {"hard_pass": 1.0, "regression_score": 1.0},
        {"hard_pass": 0.0, "regression_score": 1.0},
        {"hard_pass": 1.0, "regression_score": 0.0},
        {"hard_pass": 0.0, "regression_score": 1.0},
    ]
    s = per_dimension_summary(reports)
    assert s["strict_pass_rate"] == 0.25
    assert s["weakest_dimension"] == "hard_pass"
    assert s["dimensions"]["hard_pass"]["pass_rate"] == 0.5
