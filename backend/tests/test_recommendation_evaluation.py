"""Regression checks for the deterministic, simulated policy comparison."""

from app.evaluation.recommendation_baseline import run_evaluation


def test_seeded_scenario_uses_live_feasibility_and_is_repeatable():
    first = run_evaluation()
    second = run_evaluation()
    seeded_a, seeded_b = first["scenarios"][0], second["scenarios"][0]

    assert seeded_a["simulated"] is True
    assert seeded_a["feasible_source_count"] == 2
    assert seeded_a["recommendation_policy"]["source_base"] == "bravo"
    assert seeded_a["nearest_feasible_baseline"]["source_base"] == "bravo"
    assert seeded_a["recommendation_policy"] == seeded_b["recommendation_policy"]
    assert first["real_operational_performance_claimed"] is False


def test_equal_recovery_case_exposes_baseline_distance_advantage():
    result = run_evaluation()["scenarios"][1]

    assert result["outcome"] == "EQUAL_RECOVERY"
    assert result["recommendation_policy"]["source_base"] == "far"
    assert result["nearest_feasible_baseline"]["source_base"] == "near"
    assert result["recommendation_policy"]["expected_recovery_hours"] == result["nearest_feasible_baseline"]["expected_recovery_hours"]
    assert result["nearest_feasible_baseline"]["distance_km"] < result["recommendation_policy"]["distance_km"]
    assert result["infeasible_reasons"] == {"MINIMUM_RESERVE_VIOLATION": 1}


def test_nearest_reserve_failure_is_filtered_and_farther_fast_source_wins():
    result = run_evaluation()["scenarios"][2]

    assert result["outcome"] == "RECOMMENDATION_FASTER"
    assert result["recommendation_policy"]["source_base"] == "far"
    assert result["nearest_feasible_baseline"]["source_base"] == "near"
    assert result["baseline_minus_recommendation_recovery_hours"] == 2.5
    assert result["rejected_sources"] == [{"base_id": "closest", "reason": "MINIMUM_RESERVE_VIOLATION"}]


def test_no_source_and_infeasible_options_are_reported_without_selection():
    result = run_evaluation()["scenarios"][3]

    assert result["outcome"] == "NO_FEASIBLE_SOURCE"
    assert result["recommendation_policy"] is None
    assert result["nearest_feasible_baseline"] is None
    assert result["infeasible_source_count"] == 2
    assert result["selected_reserve_violations"] == {"recommendation": 0, "baseline": 0}
