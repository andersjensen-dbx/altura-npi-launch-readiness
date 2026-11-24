# %% [markdown]
# # 04 · Score the active launch pipeline (closed loop)
#
# Runs every time new data lands **and** every time a launch manager commits a mitigation in the app.
#
# 1. Load gold launch / component supply state (Lakeflow pipeline output).
# 2. Load **committed mitigation actions** written by the Control Tower app into **Lakebase**, which
#    flow back into Unity Catalog through **Lakehouse Sync** (CDC history table `lb_mitigation_actions_history`).
# 3. Predict production yield (UC model `npi_yield_gap_model@champion`, blended with any production-trial evidence).
# 4. Recompute supply-readiness features at the predicted yield, with and without the committed actions.
# 5. Score ramp-failure risk (`npi_launch_risk_model@champion`), explain each score, and publish:
#    `gold_launch_risk_scores`, `gold_component_readiness`, `gold_ramp_supply_curve`, `gold_launch_risk_history`
#    — CDF-enabled so Lakebase synced tables push them to the app in near real time.

# %%
import os, sys, json, warnings
sys.path.insert(0, os.path.abspath("../src"))
warnings.filterwarnings("ignore")
from datetime import datetime, timezone
import numpy as np, pandas as pd, mlflow
from mlflow import MlflowClient
from npi.env import FQ, get_spark, widget
from npi import features as F

spark = get_spark()
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")
YIELD_MODEL, RISK_MODEL = f"{FQ}.npi_yield_gap_model", f"{FQ}.npi_launch_risk_model"
SCORED_AT = datetime.now(timezone.utc).replace(microsecond=0)

portfolio = F.normalize(spark.table(f"{FQ}.gold_launch_portfolio").toPandas())
comp_all = F.normalize(spark.table(f"{FQ}.gold_launch_component_supply").toPandas())
srcq = F.normalize(spark.table(f"{FQ}.silver_supplier_qualification").toPandas())
sup = spark.table(f"{FQ}.silver_suppliers").toPandas()
demand = F.normalize(spark.table(f"{FQ}.silver_oem_demand").toPandas())
hist = portfolio[portfolio.launch_status == "LAUNCHED"]
act = portfolio[portfolio.launch_status == "ACTIVE"].reset_index(drop=True)
comp = comp_all[comp_all.launch_status == "ACTIVE"].reset_index(drop=True)
print(f"active launches: {len(act)} | components: {len(comp)} | scored_at {SCORED_AT:%Y-%m-%d %H:%M} UTC")

# %% [markdown]
# ### Committed mitigation actions from Lakebase (via Lakehouse Sync CDC history)

# %%
ACTIONS_TBL = f"{FQ}.lb_mitigation_actions_history"
if spark.catalog.tableExists(ACTIONS_TBL):
    actions = spark.sql(f"""
        SELECT * FROM (
          SELECT *, row_number() OVER (PARTITION BY action_id ORDER BY _sort_by DESC) rn
          FROM {ACTIONS_TBL} WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete'))
        WHERE rn = 1 AND _pg_change_type <> 'delete'""").toPandas()
else:
    actions = pd.DataFrame(columns=["action_id", "npi_id", "material_id", "action_type", "status", "effect_json"])
actions["material_id"] = actions.material_id.replace({"": None})
committed = actions[actions.status.isin(["APPROVED", "IN_PROGRESS", "DONE"])]
print(f"actions in Lakebase: {len(actions)} | committed (APPROVED/IN_PROGRESS/DONE): {len(committed)}")
if len(committed):
    print(committed[["action_id", "npi_id", "material_id", "action_type", "status"]].to_string(index=False))

# %% [markdown]
# ### Predicted production yield

# %%
ymodel = mlflow.sklearn.load_model(f"models:/{YIELD_MODEL}@champion")
gap = pd.Series(ymodel.predict(F.yield_matrix(act)), index=act.index).clip(lower=0)
model_yield = act.pilot_yield_pct - gap
blended, basis = F.blend_trial_yield(act, model_yield)

def score(state_actions):
    p2, c2 = F.apply_actions(act, comp, state_actions)
    py = (blended + p2.yield_gain_pts).clip(upper=p2.pilot_yield_pct)
    cr = F.component_risk(p2, c2, py)
    lf = F.launch_features(p2, cr, py)
    return p2, cr, lf, py

rmodel = mlflow.sklearn.load_model(f"models:/{RISK_MODEL}@champion")
risk_v = MlflowClient().get_model_version_by_alias(RISK_MODEL, "champion").version
_, _, lf0, _ = score(None)                         # baseline: no mitigations
p1, cr1, lf1, py1 = score(committed)               # current: committed mitigations applied
lf1["baseline_risk_score"] = rmodel.predict_proba(lf0[F.RISK_FEATURES])[:, 1]
lf1["risk_score"] = rmodel.predict_proba(lf1[F.RISK_FEATURES])[:, 1]

# %% [markdown]
# ### Explain every score (per-launch driver contributions)

# %%
def contributions(model, X):
    if hasattr(model, "named_steps"):                       # StandardScaler + LogisticRegression
        sc, lr = model[0], model[-1]
        return pd.DataFrame(sc.transform(X) * lr.coef_[0], columns=X.columns, index=X.index)
    import shap
    return pd.DataFrame(shap.TreeExplainer(model).shap_values(X), columns=X.columns, index=X.index)

contrib = contributions(rmodel, lf1[F.RISK_FEATURES])
cr1i = cr1.set_index("npi_id")
lines = spark.table(f"{FQ}.silver_coating_lines").toPandas().set_index("line_id")

def driver_text(feat, r, c):
    bind = c.sort_values("coverage_at_predicted_yield").iloc[0]
    gapc = c.sort_values("material_gap_weeks", ascending=False).iloc[0]
    return {
        "worst_material_gap_weeks": (f"{gapc.material_desc}: {gapc.lead_time_weeks:.0f}-wk lead time"
                                     + (f" + {gapc.qualification_wait_weeks:.0f}-wk PPAP wait" if gapc.qualification_wait_weeks > 0 else "")
                                     + f" vs {max(r.weeks_to_sop - 8, 0):.0f} wks until build-ahead starts ({gapc.material_gap_weeks:.0f} wks short)"),
        "supply_shortfall": f"{bind.material_desc}: qualified capacity covers {bind.coverage_at_predicted_yield:.0%} of ramp-peak need at predicted yield",
        "min_coverage_at_predicted_yield": f"{bind.material_desc}: qualified capacity covers {bind.coverage_at_predicted_yield:.0%} of ramp-peak need at predicted yield",
        "predicted_yield_gap_pts": f"Production yield predicted {r.predicted_yield_pct:.1f}% vs {r.pilot_yield_pct:.1f}% on pilot line (-{r.predicted_yield_gap_pts:.1f} pts)",
        "n_single_source_components": f"{int(r.n_single_source_components)} BOM components single-sourced at SOP",
        "n_unqualified_components": f"{int(r.n_unqualified_components)} components with no supplier qualified by ramp peak",
        "planned_line_utilization": f"Production line planned at {r.planned_line_utilization:.0%} utilization at SOP",
        "weeks_to_sop": f"{r.weeks_to_sop:.0f} weeks to SOP",
        "is_ev_oem": "EV OEM program: fixed SOP, platform design-in at stake",
        "novel_chemistry": "Novel chemistry: new-to-BTD raw materials in BOM",
        "complexity_layers": f"{int(r.complexity_layers)}-layer construction",
    }[feat]

# only actionable supply-chain drivers are surfaced (static context like segment/chemistry is shown separately)
ACTIONABLE = ["worst_material_gap_weeks", "supply_shortfall", "min_coverage_at_predicted_yield", "predicted_yield_gap_pts",
              "n_single_source_components", "n_unqualified_components", "planned_line_utilization"]
drivers, binding = [], []
for i, r in lf1.iterrows():
    c = cr1i.loc[[r.npi_id]].reset_index()
    top = contrib.loc[i, ACTIONABLE].sort_values(ascending=False)
    top = top[top > 0].head(3)
    if "supply_shortfall" in top.index and "min_coverage_at_predicted_yield" in top.index:
        top = top.drop("min_coverage_at_predicted_yield")
    drivers.append(json.dumps([{"feature": f, "label": F.FEATURE_LABELS[f], "impact": round(float(v), 3),
                                "detail": driver_text(f, r, c)} for f, v in top.items()]))
    b = c.sort_values("coverage_at_predicted_yield").iloc[0]
    binding.append((b.material_id, b.material_desc))
lf1["top_drivers_json"] = drivers
lf1["binding_component_id"] = [b[0] for b in binding]
lf1["binding_component_desc"] = [b[1] for b in binding]

# %% [markdown]
# ### Publish serving tables

# %%
h = hist.copy()
p_platform = (h[h.ramp_failed & h.market_segment.isin(["EV_OEM", "AUTO_TIER1"])].platform_lost.mean())
print(f"historical P(platform lost | failed ramp, auto/EV) = {p_platform:.2f}")

meta = act.set_index("npi_id")
out = lf1.set_index("npi_id").join(meta[["product_code", "product_name", "family_name", "oem_customer", "oem_program",
                                         "plant", "production_line", "sop_date", "current_gate", "npi_manager",
                                         "year1_revenue_usd", "program_lifetime_value_usd", "region",
                                         "production_trial_yield_pct"]], rsuffix="_m")
out["yield_basis"] = basis.values
out["risk_tier"] = np.select([out.risk_score >= 0.6, out.risk_score >= 0.25], ["HIGH", "MEDIUM"], "LOW")
out["revenue_at_risk_usd"] = (out.risk_score * out.year1_revenue_usd).round(0)
auto = out.market_segment.isin(["EV_OEM", "AUTO_TIER1"])
out["platform_value_at_risk_usd"] = np.where(auto, out.risk_score * p_platform * out.program_lifetime_value_usd, 0).round(0)
out["actions_applied"] = p1.set_index("npi_id").actions_applied
out["risk_model_version"] = int(risk_v)
out["scored_at"] = SCORED_AT
cols = ["product_code", "product_name", "family_name", "market_segment", "oem_customer", "oem_program", "region",
        "plant", "production_line", "sop_date", "weeks_to_sop", "current_gate", "npi_manager", "year1_revenue_usd",
        "program_lifetime_value_usd", "pilot_yield_pct", "production_trial_yield_pct", "predicted_yield_pct",
        "yield_basis", "predicted_yield_gap_pts", "min_coverage_at_predicted_yield", "worst_material_gap_weeks",
        "n_single_source_components", "n_unqualified_components", "planned_line_utilization", "baseline_risk_score",
        "risk_score", "risk_tier", "revenue_at_risk_usd", "platform_value_at_risk_usd", "binding_component_id",
        "binding_component_desc", "top_drivers_json", "actions_applied", "risk_model_version", "scored_at"]
scores = out[cols].reset_index()
for c in ["risk_score", "baseline_risk_score"]:
    scores[c] = scores[c].round(4)
for c in ["predicted_yield_pct", "predicted_yield_gap_pts", "min_coverage_at_predicted_yield"]:
    scores[c] = scores[c].astype(float).round(3)

compo = cr1[["npi_id", "product_code", "material_id", "material_desc", "material_category", "uom", "is_novel_material",
             "lead_time_weeks", "sources", "n_approved_sources", "n_sources_qualified_by_peak", "earliest_qualification_date",
             "latest_pending_qualification_date", "qualification_wait_weeks", "required_peak_weekly_at_pilot_yield",
             "required_peak_weekly_at_predicted_yield", "capacity_available_for_launch", "coverage_at_pilot_yield",
             "coverage_at_predicted_yield", "weekly_shortfall_at_peak", "material_gap_weeks", "readiness_status",
             "open_po_qty", "unconfirmed_po_lines", "buffer_weeks"]].copy()
compo["sources"] = compo.sources.map(lambda a: ", ".join(a) if a is not None else "")
compo["is_novel_material"] = compo.is_novel_material.astype(str).str.lower().isin(["true", "1"])
compo["required_peak_weekly_at_predicted_yield"] = compo.required_peak_weekly_at_predicted_yield.round(1)
compo["scored_at"] = SCORED_AT

# %% [markdown]
# Ramp curve per launch: weekly OEM demand vs. what the **binding component's** qualified supply can
# support, week by week as pending PPAPs complete (actions applied: pull-ins and capacity reservations).

# %%
curve_rows = []
dem = demand[demand.npi_id.isin(act.npi_id)]
for _, r in scores.iterrows():
    m = r.binding_component_id
    c = compo[(compo.npi_id == r.npi_id) & (compo.material_id == m)].iloc[0]
    s = srcq[srcq.material_id == m].copy()
    a = committed[(committed.npi_id == r.npi_id) & ((committed.material_id == m) | committed.material_id.isna())]
    pull = sum(json.loads(e or "{}").get("qual_pull_in_weeks", 0) for t, e in zip(a.action_type, a.effect_json) if t == "DUAL_SOURCE_EXPEDITE")
    upl = np.prod([1 + json.loads(e or "{}").get("capacity_uplift_pct", 0) / 100 for t, e in zip(a.action_type, a.effect_json) if t == "CAPACITY_RESERVATION"] or [1])
    ramp_f = np.prod([json.loads(e or "{}").get("ramp_peak_factor", 1) for t, e in zip(a.action_type, a.effect_json) if t == "PHASED_RAMP_WITH_OEM"] or [1])
    s["avail_from"] = pd.to_datetime(s.ppap_planned_date) - pd.to_timedelta(np.where(pd.to_datetime(s.ppap_planned_date) > pd.Timestamp(r.sop_date) + pd.Timedelta(weeks=8), pull * 7, 0), unit="D")
    mat = comp[(comp.npi_id == r.npi_id) & (comp.material_id == m)].iloc[0]
    per_m2 = mat.required_peak_weekly_at_pilot_yield / mat.peak_weekly_demand_m2 * (mat.pilot_yield_pct / 100)  # component units per m2 good output
    for _, d in dem[dem.npi_id == r.npi_id].iterrows():
        wk = pd.Timestamp(d.week_start)
        cap = s.loc[s.avail_from <= wk, "qualified_weekly_capacity"].sum() * upl - (0 if mat.is_novel_material in (True, "true") else mat.base_business_weekly_demand)
        dm2 = d.forecast_m2 * ramp_f
        need_pred = dm2 / (r.predicted_yield_pct / 100) * per_m2
        curve_rows.append({"npi_id": r.npi_id, "week_start": wk.date(), "week_rel_sop": int(d.week_rel_sop),
                           "oem_demand_m2": round(dm2, 0), "binding_component_id": m,
                           "binding_component_desc": r.binding_component_desc,
                           "component_need_at_pilot_yield": round(dm2 / (r.pilot_yield_pct / 100) * per_m2, 0),
                           "component_need_at_predicted_yield": round(need_pred, 0),
                           "component_supply_available": round(max(cap, 0), 0),
                           "supportable_output_m2": round(max(cap, 0) / per_m2 * r.predicted_yield_pct / 100, 0),
                           "shortfall_m2": round(max(0.0, dm2 - max(cap, 0) / per_m2 * r.predicted_yield_pct / 100), 0)})
curve = pd.DataFrame(curve_rows)

# %%
def publish(pdf, name, comment, key):
    tbl = f"{FQ}.{name}"
    sdf = spark.createDataFrame(pdf)
    sdf.createOrReplaceTempView(f"v_{name}")
    if not spark.catalog.tableExists(tbl):
        spark.sql(f"CREATE TABLE {tbl} COMMENT '{comment}' TBLPROPERTIES (delta.enableChangeDataFeed = true) AS SELECT * FROM v_{name}")
        for k in key.split(","):
            spark.sql(f"ALTER TABLE {tbl} ALTER COLUMN {k.strip()} SET NOT NULL")
    else:
        spark.sql(f"INSERT OVERWRITE TABLE {tbl} SELECT * FROM v_{name}")
    print(f"published {tbl}: {len(pdf)} rows")

publish(scores, "gold_launch_risk_scores", "Ramp-failure risk score per ACTIVE NPI launch with explanation, revenue and OEM-platform value at risk, and effect of committed mitigations. Grain: npi_id.", "npi_id")
publish(compo, "gold_component_readiness", "Supply readiness per active launch x BOM component at PREDICTED production yield: coverage, shortfall, PPAP timing, RED/AMBER/GREEN. Grain: npi_id, material_id.", "npi_id,material_id")
publish(curve, "gold_ramp_supply_curve", "Weekly ramp curve per active launch: OEM demand vs output supportable by the binding component supply. Grain: npi_id, week_rel_sop.", "npi_id,week_rel_sop")
hist_row = scores[["npi_id", "risk_score", "baseline_risk_score", "actions_applied", "scored_at"]]
spark.createDataFrame(hist_row).write.mode("append").option("mergeSchema", "true").saveAsTable(f"{FQ}.gold_launch_risk_history")

# %% [markdown]
# ### Result: the active pipeline

# %%
pd.set_option("display.width", 250)
v = scores.sort_values("risk_score", ascending=False)
print(f"Active launches: {len(v)} | HIGH: {(v.risk_tier=='HIGH').sum()} | MEDIUM: {(v.risk_tier=='MEDIUM').sum()} | LOW: {(v.risk_tier=='LOW').sum()}")
print(f"Year-1 revenue in pipeline: ${v.year1_revenue_usd.sum()/1e6:,.1f}M | revenue at risk: ${v.revenue_at_risk_usd.sum()/1e6:,.1f}M | "
      f"OEM platform value at risk: ${v.platform_value_at_risk_usd.sum()/1e6:,.1f}M")
print(v[["npi_id", "product_code", "oem_customer", "sop_date", "risk_tier", "baseline_risk_score", "risk_score",
         "revenue_at_risk_usd", "binding_component_desc"]].head(12).to_string(index=False))

# %%
hero = scores[scores.npi_id == "NPI-2027-014"].iloc[0]
print(f"{hero.product_name} | {hero.oem_customer} {hero.oem_program} | SOP {hero.sop_date} ({hero.weeks_to_sop:.0f} wks)")
print(f"risk {hero.risk_score:.0%} ({hero.risk_tier}) | baseline {hero.baseline_risk_score:.0%} | actions applied {hero.actions_applied}")
print(f"yield: pilot {hero.pilot_yield_pct:.1f}% -> predicted {hero.predicted_yield_pct:.1f}% [{hero.yield_basis}]")
for d in json.loads(hero.top_drivers_json):
    print(f"  driver: {d['detail']}")
print(compo[compo.npi_id == "NPI-2027-014"][["material_desc", "coverage_at_pilot_yield", "coverage_at_predicted_yield",
      "weekly_shortfall_at_peak", "material_gap_weeks", "readiness_status"]].to_string(index=False))
