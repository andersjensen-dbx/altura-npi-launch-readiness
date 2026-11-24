# %% [markdown]
# # 03 · Train the launch-readiness models (MLflow + Unity Catalog)
#
# Two models, trained on **420 historical BTD launches (2020-2026)** evaluated *as of their G3
# scale-up gate* — i.e. only what the NPI steering committee could have known at that decision:
#
# 1. **Yield-gap model** (regression): predicts the pilot → production yield drop from
#    construction complexity, chemistry novelty, pilot-vs-production line technology fit, line age
#    and pilot evidence. Today's ramp plans implicitly assume *zero* gap.
# 2. **Launch ramp-failure model** (classification): P(launch slips >2 weeks or runs <85% OTIF in its
#    first 90 days) from supply-readiness features computed at the *predicted* production yield.
#
# Validation uses a **temporal holdout** (train: SOP 2020-2024, test: SOP 2025-2026) — the honest
# setup for "would this have warned us about last year's launches?". Both models are registered in
# Unity Catalog with a `@champion` alias consumed by the scoring job.

# %%
import os, sys, warnings
sys.path.insert(0, os.path.abspath("../src"))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, mlflow, shap
from mlflow.models import infer_signature
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_predict, KFold
from sklearn.metrics import (mean_absolute_error, roc_auc_score, average_precision_score, brier_score_loss)
from npi.env import FQ, get_spark, in_databricks
from npi import features as F

spark = get_spark()
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")
user = spark.sql("select current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/npi-launch-readiness")
YIELD_MODEL, RISK_MODEL = f"{FQ}.npi_yield_gap_model", f"{FQ}.npi_launch_risk_model"

portfolio = F.normalize(spark.table(f"{FQ}.gold_launch_portfolio").toPandas())
comp = F.normalize(spark.table(f"{FQ}.gold_launch_component_supply").toPandas())
hist = portfolio[portfolio.launch_status == "LAUNCHED"].reset_index(drop=True)
print(f"historical launches: {len(hist)}  active: {(portfolio.launch_status=='ACTIVE').sum()}  components: {len(comp)}")
print(f"historical ramp-failure rate: {hist.ramp_failed.mean():.1%}")

# %% [markdown]
# ## 1 · Yield-gap model
# Target = pilot yield − realized first-12-week production yield (MES). Baseline = today's planning
# assumption (gap = 0, i.e. plan at pilot yield).

# %%
hist["sop_year"] = pd.to_datetime(hist.sop_date).dt.year
train_m, test_m = hist.sop_year <= 2024, hist.sop_year >= 2025
Xy = F.yield_matrix(hist)
yy = hist.pilot_yield_pct - hist.realized_production_yield_pct

with mlflow.start_run(run_name="yield_gap_model") as run_y:
    cands = {"gbm": GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=7),
             "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0))}
    res = {}
    for name, m in cands.items():
        m.fit(Xy[train_m], yy[train_m])
        res[name] = (m, mean_absolute_error(yy[test_m], m.predict(Xy[test_m])))
    base_mae = mean_absolute_error(yy[test_m], np.zeros(test_m.sum()))
    best = min(res, key=lambda k: res[k][1])
    ymodel = res[best][0]
    for k, (_, mae) in res.items():
        mlflow.log_metric(f"test_mae_{k}", mae)
    mlflow.log_metric("test_mae_baseline_plan_at_pilot_yield", base_mae)
    mlflow.log_params({"selected": best, "train_years": "2020-2024", "test_years": "2025-2026"})
    mlflow.sklearn.log_model(ymodel, name="model", signature=infer_signature(Xy, ymodel.predict(Xy)),
                             input_example=Xy.head(3), registered_model_name=YIELD_MODEL)
print(f"Yield-gap MAE (pts) on 2025-26 launches | plan-at-pilot baseline: {base_mae:.2f} | "
      + " | ".join(f"{k}: {v[1]:.2f}" for k, v in res.items()) + f"  -> selected {best}")

# %% [markdown]
# ## 2 · Launch ramp-failure model
# Out-of-fold predicted yields for historical launches (no leakage), then supply-readiness features
# at the predicted yield.

# %%
oof_gap = cross_val_predict(ymodel, Xy, yy,
                            cv=KFold(5, shuffle=True, random_state=7))
hist_pred_yield = hist.pilot_yield_pct - pd.Series(oof_gap).clip(lower=0)
crisk_h = F.component_risk(hist, comp[comp.launch_status == "LAUNCHED"], hist_pred_yield)
feat_h = F.launch_features(hist, crisk_h, hist_pred_yield).merge(
    hist[["npi_id", "ramp_failed", "sop_year", "year1_revenue_usd", "expedite_cost_usd", "eo_writeoff_usd",
          "deferred_revenue_usd", "lost_platform_value_usd", "platform_lost"]], on="npi_id")
X, y = feat_h[F.RISK_FEATURES], feat_h.ramp_failed.astype(int)
tr, te = feat_h.sop_year <= 2024, feat_h.sop_year >= 2025
print(f"train n={tr.sum()} (fail {y[tr].mean():.1%}) | test n={te.sum()} (fail {y[te].mean():.1%})")
print(X.describe().T[["mean", "min", "max"]].round(2).to_string())

# %%
with mlflow.start_run(run_name="launch_risk_model") as run_r:
    cands = {"gbm": GradientBoostingClassifier(n_estimators=250, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=7),
             "logreg": make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))}
    scores = {}
    for name, m in cands.items():
        m.fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]
        scores[name] = {"auc": roc_auc_score(y[te], p), "pr_auc": average_precision_score(y[te], p),
                        "brier": brier_score_loss(y[te], p), "model": m, "p": p}
        for k in ("auc", "pr_auc", "brier"):
            mlflow.log_metric(f"test_{k}_{name}", scores[name][k])
    champ = max(scores, key=lambda k: scores[k]["auc"])
    rmodel, p_te = scores[champ]["model"], scores[champ]["p"]
    mlflow.log_params({"selected": champ, "features": ",".join(F.RISK_FEATURES), "label": "slip>2w or OTIF90<85%"})
    mlflow.sklearn.log_model(rmodel, name="model", signature=infer_signature(X, rmodel.predict_proba(X)[:, 1]),
                             input_example=X.head(3), registered_model_name=RISK_MODEL)
for k, v in scores.items():
    print(f"{k:7s} test AUC {v['auc']:.3f} | PR-AUC {v['pr_auc']:.3f} | Brier {v['brier']:.3f}")
print(f"champion: {champ}")

# %% [markdown]
# ### Global drivers (SHAP) — what actually predicts a failed ramp

# %%
est = rmodel if champ == "gbm" else rmodel[-1]
Xs = X if champ == "gbm" else pd.DataFrame(rmodel[0].transform(X), columns=X.columns)
sv = shap.TreeExplainer(est).shap_values(Xs) if champ == "gbm" else shap.LinearExplainer(est, Xs).shap_values(Xs)
imp = pd.Series(np.abs(sv).mean(0), index=X.columns).sort_values(ascending=False)
print((imp / imp.sum()).round(3).rename(index=F.FEATURE_LABELS).to_string())

# %% [markdown]
# ## 3 · Back-test: would the Control Tower have paid for itself on 2025-26 launches?
# Flag the top 30% riskiest launches at G3. Assumption (documented, conservative): mitigation
# playbook avoids **50%** of failure cost on flagged launches that would have failed; deferred
# revenue valued at a **35% contribution margin**; lost OEM platforms valued at lifetime revenue × 35%.

# %%
bt = feat_h[te].copy(); bt["risk"] = p_te
bt["failure_cost"] = np.where(bt.ramp_failed, bt.expedite_cost_usd + bt.eo_writeoff_usd
                              + 0.35 * bt.deferred_revenue_usd + 0.35 * bt.lost_platform_value_usd, 0.0)
thr = bt.risk.quantile(0.70)
flag = bt.risk >= thr
years = bt.sop_year.nunique()
cap = bt.loc[flag & bt.ramp_failed, "failure_cost"].sum() / bt.failure_cost.sum()
print(f"Test launches: {len(bt)} over {years} years | failed: {bt.ramp_failed.sum()}")
print(f"Top-30% flag catches {(flag & bt.ramp_failed).sum()}/{bt.ramp_failed.sum()} failures "
      f"(recall {(flag & bt.ramp_failed).sum()/bt.ramp_failed.sum():.0%}, precision {bt[flag].ramp_failed.mean():.0%} vs base {bt.ramp_failed.mean():.0%})")
print(f"Share of total failure cost sitting in flagged launches: {cap:.0%}")
print(f"Total failure cost (margin view) per year: ${bt.failure_cost.sum()/years/1e6:,.1f}M")
avoid = 0.5 * bt.loc[flag & bt.ramp_failed, "failure_cost"].sum() / years
print(f"Estimated avoidable cost per year @50% mitigation success: ${avoid/1e6:,.1f}M")
platforms = bt[flag & bt.platform_lost]
print(f"OEM platforms lost in flagged set: {len(platforms)} of {bt.platform_lost.sum()} (lifetime value ${platforms.lost_platform_value_usd.sum()/1e6:,.0f}M)")
mlflow.log_metrics({"backtest_recall_top30": float((flag & bt.ramp_failed).sum() / bt.ramp_failed.sum()),
                    "backtest_avoidable_cost_per_year_usd": float(avoid)}, run_id=run_r.info.run_id)

# %% [markdown]
# ## 4 · Promote to `@champion` in Unity Catalog

# %%
from mlflow import MlflowClient
c = MlflowClient()
for name in (YIELD_MODEL, RISK_MODEL):
    v = max(int(m.version) for m in c.search_model_versions(f"name='{name}'"))
    c.set_registered_model_alias(name, "champion", v)
    c.update_registered_model(name, description={
        YIELD_MODEL: "Predicts pilot-to-production yield gap (pts) for BTD NPI launches. Trained on MES yields of 2020-2024 launches.",
        RISK_MODEL: "P(launch ramp failure: slip >2 weeks or first-90-day OTIF <85%) from supply-readiness features at predicted yield."}[name])
    print(f"{name} v{v} -> @champion")
