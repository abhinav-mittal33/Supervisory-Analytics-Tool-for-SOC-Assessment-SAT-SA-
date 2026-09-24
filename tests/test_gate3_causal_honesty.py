"""Gate 3 — Causal honesty test (docs/validation_plan.md / Section 12).

"Validate on synthetic data with one known confounder deliberately withheld from the
estimator. The engine must either recover the correct direction under a documented
assumption, or visibly flag the estimate as unreliable — silently getting the
direction wrong is the only unacceptable outcome."

Two scenarios, both run through the SAME pipeline (estimate -> robustness_value ->
decide), with no scenario-specific tuning of the decision logic itself:

1. A strong, clean, unconfounded effect: the engine should recover the correct
   direction confidently (ACT).
2. A moderate true effect deliberately confounded strongly enough that withholding
   the confounder actually flips the naive estimate's sign (verified against a
   reference estimate that DOES include the confounder, which only this test harness
   is allowed to peek at — the engine itself never sees it, matching "withheld from
   the estimator"): the engine must not silently ACT on the wrong-signed result.
"""
from satsa.moat2.causal_model import estimate_effect
from satsa.moat2.decision import ROBUSTNESS_VALUE_THRESHOLD, decide
from satsa.moat2.sensitivity import robustness_value
from satsa.moat2.synthetic_causal_data import generate_intervention_scenario


def test_strong_clean_effect_is_recovered_and_acted_on():
    df = generate_intervention_scenario(
        n=4000, seed=1, true_effect=4.0,
        confounder_strength_on_treatment=0.0, confounder_strength_on_outcome=0.0,
    )
    est = estimate_effect(df, treatment="T", outcome="Y", confounders=())
    rv = robustness_value(est.t_statistic, est.df_resid)
    decision = decide(est.effect, est.ci_low, est.ci_high, rv)

    print(f"[clean] effect={est.effect:.3f} CI=[{est.ci_low:.3f},{est.ci_high:.3f}] RV={rv:.3f} decision={decision}")
    assert est.effect > 0, "true effect is positive — must recover the correct direction"
    assert rv >= ROBUSTNESS_VALUE_THRESHOLD, "a strong, clean effect should clear the robustness bar"
    assert decision == "ACT"


def test_withheld_confounder_does_not_silently_act_on_the_wrong_direction():
    df = generate_intervention_scenario(
        n=4000, seed=1, true_effect=0.5,
        confounder_strength_on_treatment=4.0, confounder_strength_on_outcome=-4.0,
    )

    # Reference only: the test harness's own ground-truth check, confirming the
    # confounder genuinely biases the naive estimate — the engine below never sees C.
    reference = estimate_effect(df, treatment="T", outcome="Y", confounders=("C",))
    assert reference.effect > 0, "with the confounder included, the true positive direction should be recovered"

    est = estimate_effect(df, treatment="T", outcome="Y", confounders=())  # C withheld from the estimator
    rv = robustness_value(est.t_statistic, est.df_resid)
    decision = decide(est.effect, est.ci_low, est.ci_high, rv)

    print(f"[confounded] with-C={reference.effect:.3f} without-C={est.effect:.3f} RV={rv:.3f} decision={decision}")

    assert est.effect < 0, "test is only meaningful if withholding the confounder actually flipped the sign"
    # The actual Gate 3 requirement: whatever the naive point estimate says, the
    # engine must not present it as an actionable, high-confidence ACT.
    assert decision == "INVESTIGATE_MORE"
    assert rv < ROBUSTNESS_VALUE_THRESHOLD
