"""
Feature engineering shared by model TRAINING (historical launches, as of their G3 gate) and
SCORING (active launches, as of today, with committed mitigation actions applied).
One code path -> no train/serve skew.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

YIELD_FEATURES = ["complexity_layers", "novel_chemistry", "pilot_to_line_tech_mismatch",
                  "production_line_age_years", "pilot_runs_capped", "pilot_yield_pct",
                  "fam_SAF", "fam_TIT", "fam_FBT", "fam_OCA", "fam_LVT", "fam_ADT", "fam_DGT"]

RISK_FEATURES = ["weeks_to_sop", "min_coverage_at_predicted_yield", "supply_shortfall",
                 "worst_material_gap_weeks", "n_single_source_components", "n_unqualified_components",
                 "predicted_yield_gap_pts", "planned_line_utilization", "is_ev_oem",
                 "complexity_layers", "novel_chemistry"]

FEATURE_LABELS = {
    "min_coverage_at_predicted_yield": "Qualified supply coverage of ramp need (at predicted yield)",
    "supply_shortfall": "Supply shortfall vs ramp peak",
    "worst_material_gap_weeks": "Material gap: lead time + PPAP wait vs build-ahead start",
    "n_single_source_components": "Single-sourced components",
    "n_unqualified_components": "Components with no source qualified by ramp peak (SOP+8 wks)",
    "predicted_yield_gap_pts": "Pilot-to-production yield gap",
    "planned_line_utilization": "Production line utilization at SOP",
    "weeks_to_sop": "Weeks to SOP",
    "is_ev_oem": "EV OEM program (fixed SOP, platform design-in)",
    "complexity_layers": "Construction complexity (layers)",
    "novel_chemistry": "Novel chemistry",
}


def yield_matrix(portfolio: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=portfolio.index)
    X["complexity_layers"] = portfolio.complexity_layers.astype(float)
    X["novel_chemistry"] = portfolio.novel_chemistry.astype(bool).astype(float)
    X["pilot_to_line_tech_mismatch"] = portfolio.pilot_to_line_tech_mismatch.astype(float)
    X["production_line_age_years"] = portfolio.production_line_age_years.astype(float)
    X["pilot_runs_capped"] = portfolio.pilot_runs.clip(upper=10).astype(float)
    X["pilot_yield_pct"] = portfolio.pilot_yield_pct.astype(float)
    for f in ["SAF", "TIT", "FBT", "OCA", "LVT", "ADT", "DGT"]:
        X[f"fam_{f}"] = (portfolio.family_code == f).astype(float)
    return X[YIELD_FEATURES]


def blend_trial_yield(portfolio: pd.DataFrame, model_pred_yield: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Combine model-predicted production yield with production-trial evidence (if any).
    2+ trial runs -> 60% weight on observed trials. Returns (yield, source label)."""
    trial = portfolio.production_trial_yield_pct
    n = portfolio.production_trial_runs.fillna(0)
    w = np.where(n >= 2, 0.6, np.where(n == 1, 0.35, 0.0))
    blended = np.where(n > 0, w * trial.fillna(0) + (1 - w) * model_pred_yield, model_pred_yield)
    src = np.where(n > 0, "model + production trials", "model (pilot evidence only)")
    return pd.Series(blended, index=portfolio.index), pd.Series(src, index=portfolio.index)


def apply_actions(portfolio: pd.DataFrame, comp: pd.DataFrame, actions: pd.DataFrame | None):
    """Apply committed mitigation actions (from Lakebase) to launch + component state.
    Only actions in status APPROVED / IN_PROGRESS / DONE count."""
    portfolio, comp = portfolio.copy(), comp.copy()
    portfolio["yield_gain_pts"] = 0.0
    portfolio["actions_applied"] = 0
    comp["buffer_weeks"] = 0.0
    if actions is None or actions.empty:
        return portfolio, comp
    act = actions[actions.status.isin(["APPROVED", "IN_PROGRESS", "DONE"])]
    for _, a in act.iterrows():
        eff = a.effect_json if isinstance(a.effect_json, dict) else json.loads(a.effect_json or "{}")
        lm = portfolio.npi_id == a.npi_id
        cm = (comp.npi_id == a.npi_id) & ((comp.material_id == a.material_id) if a.material_id else True)
        if not lm.any():
            continue
        portfolio.loc[lm, "actions_applied"] += 1
        t = a.action_type
        if t == "DUAL_SOURCE_EXPEDITE":
            wk = pd.Timedelta(weeks=float(eff.get("qual_pull_in_weeks", 6)))
            pend = comp.latest_pending_qualification_date
            ok = cm & pend.notna() & ((pd.to_datetime(pend) - wk) <= pd.to_datetime(comp.sop_date) + pd.Timedelta(weeks=8))
            comp.loc[ok, "capacity_available_for_launch"] = comp.loc[ok, "capacity_all_sources"] - comp.loc[ok, "base_business_weekly_demand"]
            comp.loc[ok, "n_sources_qualified_by_peak"] = comp.loc[ok, "n_approved_sources"]
            comp.loc[cm, "qualification_wait_weeks"] = (comp.loc[cm, "qualification_wait_weeks"] - wk.days / 7).clip(lower=0)
        elif t == "CAPACITY_RESERVATION":
            # uplift applies to GROSS qualified capacity; base-business draw is unchanged
            u = float(eff.get("capacity_uplift_pct", 35)) / 100
            gross = comp.loc[cm, "capacity_available_for_launch"] + comp.loc[cm, "base_business_weekly_demand"]
            comp.loc[cm, "capacity_available_for_launch"] = gross * (1 + u) - comp.loc[cm, "base_business_weekly_demand"]
        elif t == "PULL_AHEAD_BUY":
            comp.loc[cm, "buffer_weeks"] += float(eff.get("buffer_weeks", 6))
        elif t == "YIELD_SPRINT":
            portfolio.loc[lm, "yield_gain_pts"] += float(eff.get("yield_gain_pts", 6))
        elif t == "LINE_REALLOCATION":
            portfolio.loc[lm, "planned_line_utilization"] += float(eff.get("utilization_delta", -0.12))
        elif t == "PHASED_RAMP_WITH_OEM":
            f = float(eff.get("ramp_peak_factor", 0.8))
            comp.loc[comp.npi_id == a.npi_id, "required_peak_weekly_at_pilot_yield"] *= f
    return portfolio, comp


def component_risk(portfolio: pd.DataFrame, comp: pd.DataFrame, pred_yield: pd.Series) -> pd.DataFrame:
    """Per launch x component readiness at the PREDICTED production yield."""
    py = portfolio.set_index("npi_id")
    c = comp.copy()
    c["pilot_yield_pct"] = c.npi_id.map(py.pilot_yield_pct)
    c["predicted_yield_pct"] = c.npi_id.map(pd.Series(pred_yield.values, index=portfolio.npi_id))
    c["required_peak_weekly_at_predicted_yield"] = (c.required_peak_weekly_at_pilot_yield
                                                    * c.pilot_yield_pct / c.predicted_yield_pct)
    c["coverage_at_predicted_yield"] = (c.capacity_available_for_launch
                                        / c.required_peak_weekly_at_predicted_yield).round(3)
    c["weekly_shortfall_at_peak"] = (c.required_peak_weekly_at_predicted_yield
                                     - c.capacity_available_for_launch).clip(lower=0).round(0)
    buf = c["buffer_weeks"] if "buffer_weeks" in c else pd.Series(0.0, index=c.index)
    novel = c.is_novel_material.astype(str).str.lower().isin(["true", "1"])
    c["material_gap_weeks"] = np.where(
        novel,
        np.minimum(c.lead_time_weeks, 30) + c.qualification_wait_weeks - (c.weeks_to_sop - 8) - buf.fillna(0),
        -4.0).round(1)
    c["readiness_status"] = np.select(
        [(c.coverage_at_predicted_yield < 0.9) | (c.material_gap_weeks > 2) | (c.n_sources_qualified_by_peak == 0),
         (c.coverage_at_predicted_yield < 1.1) | (c.material_gap_weeks > 0) | (c.n_sources_qualified_by_peak == 1)],
        ["RED", "AMBER"], "GREEN")
    return c


def launch_features(portfolio: pd.DataFrame, comp_risk: pd.DataFrame, pred_yield: pd.Series) -> pd.DataFrame:
    g = comp_risk.groupby("npi_id").agg(
        min_coverage_at_predicted_yield=("coverage_at_predicted_yield", "min"),
        worst_material_gap_weeks=("material_gap_weeks", "max"),
        n_single_source_components=("n_sources_qualified_by_peak", lambda s: int((s <= 1).sum())),
        n_unqualified_components=("n_sources_qualified_by_peak", lambda s: int((s == 0).sum())),
    )
    f = portfolio.set_index("npi_id")[["weeks_to_sop", "planned_line_utilization", "market_segment",
                                       "complexity_layers", "novel_chemistry", "pilot_yield_pct"]].join(g)
    f["predicted_yield_pct"] = pd.Series(pred_yield.values, index=portfolio.npi_id)
    f["predicted_yield_gap_pts"] = (f.pilot_yield_pct - f.predicted_yield_pct).clip(lower=0)
    f["min_coverage_at_predicted_yield"] = f.min_coverage_at_predicted_yield.clip(upper=5)
    f["supply_shortfall"] = (1 - f.min_coverage_at_predicted_yield).clip(lower=0, upper=0.8)
    f["is_ev_oem"] = (f.market_segment == "EV_OEM").astype(float)
    f["novel_chemistry"] = f.novel_chemistry.astype(bool).astype(float)
    f["complexity_layers"] = f.complexity_layers.astype(float)
    return f.reset_index()


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Spark DECIMAL -> float, DATE -> pandas datetime-compatible; keeps other columns."""
    from decimal import Decimal
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object and out[c].map(lambda v: isinstance(v, Decimal)).any():
            out[c] = out[c].astype(float)
    return out
