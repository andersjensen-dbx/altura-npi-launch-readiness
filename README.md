# Altura Bonding & Tapes: NPI Launch Readiness Control Tower

> **Outcome:** catch pilot-to-production supply failures 16+ weeks before SOP, while there is still time to act, and protect the OEM platforms behind them.
> In a back-test on 2025-26 launches the Control Tower flags **66% of failed ramps** in the top 30% riskiest launches. Those launches carry **91% of failure cost** and **6 of 7 lost OEM platforms**, which is about **$19.8M/yr of avoidable cost**. Today's pipeline has **$57.3M of year-1 revenue at risk** before mitigation, already down to **$52.0M** after three in-flight actions, plus **$57M of OEM platform value at risk**.

*Customer: Altura Industries (fictional) · Vertical: Manufacturing (diversified industrial), Bonding & Tapes · Domain: supply chain / new product introduction (NPI).
All data is synthetic; products, suppliers, OEMs and plants are fictional.*

---

## 1 · The business problem
Altura is very good at taking a new tape from idea to a validated pilot. It struggles to **scale that product from pilot to production**, and the reason is in the supply chain:

- The **ramp plan is built on pilot assumptions**: pilot-line yields (about 91%) and pilot-qualified, often **single-source, new-to-Altura materials** (foam cores, fluorosilicone liners, thermal fillers).
- On the production line, yield drops **10-20 points**. At the same time, a component's only qualified supplier can't cover the ramp peak, or a second source's **PPAP lands after SOP**.
- Nobody sees this across **SAP** (BOM, approved sources, POs), **MES** (yields), **PLM** (stage gates) and **OEM EDI** (demand). The gap surfaces as expedites, low OTIF and missed SOPs.
- For **OEM-specified EV/auto tapes** a missed SOP isn't a delayed sale. The OEM qualifies a competitor and **Altura loses the platform for 5-7 years**.

In the synthetic history, **31.9%** of launches that passed pilot missed their ramp. That costs about **$43.6M/yr** (margin view), and **22 OEM platforms** were lost in 2020-26.

## 2 · What the solution does
A **Launch Readiness Control Tower** for the G3/G4 steering committee, NPI launch managers and buyers:

1. **Predicts production yield** from pilot evidence, line-technology fit and production trials. Today's practice is to assume the pilot yield.
2. **Recomputes BOM supply coverage** at that yield against capacity qualified by the ramp peak, net of base-business demand. It also checks **lead time + PPAP timing** against the build-ahead window.
3. **Scores ramp-failure risk** and shows the *actionable* drivers, plus revenue and OEM-platform value at risk.
4. **Explains and recommends**: an LLM steering-committee brief per launch, and a tool-calling **Mitigation Advisor** that **simulates mitigation packages with the production models** before recommending one.
5. **Closes the loop**: a manager approves actions in the app. They are written to Lakebase, flow back to the lakehouse (Lakehouse Sync), trigger a re-score, and the new risk appears in the app within minutes.

**Hero example:** AFT-7200 structural battery-enclosure foam tape for Northstar Motors' NSM-EVX9 EV program, SOP 15-Mar-2027 (16 weeks out). Risk is **93%** with **$17.1M** at risk. The drivers:
- The FC-220 foam core has one qualified supplier, whose capacity was cut this morning (SCD2 history). It covers only **71%** of ramp-peak need at the predicted 70.7% yield.
- Kvarn's PPAP is due in June.
- There is a 14-week lead time against 8 weeks until build-ahead starts.

Committing the dual-source expedite + pull-ahead + yield sprint package in the app takes AFT-7200 from **93% to 15%** risk and protects **$14.4M**. Lakebase → Lakehouse Sync → triggered re-score → app took **3.6 minutes** end to end (`notebooks/09_closed_loop_proof.ipynb`).

## 3 · Integrated data journey (all six required stages)
```
SAP / MES / PLM / OEM EDI extracts → UC Volume
 → Lakeflow SDP (Auto Loader bronze → silver + expectations + AUTO CDC SCD2 → gold MVs)
 → Unity Catalog (tags, certification, PK/FK, metric views, ABAC mask + row filter, lineage)
 → ML: yield-gap + ramp-risk models (MLflow, UC @champion) → scoring job (applies committed actions)
 → GenAI: ai_query briefs + Mitigation Advisor agent (Model Serving, OBO, MLflow eval)
 → Lakebase: synced serving tables + OLTP actions → Lakehouse Sync back to UC → event-driven re-score
 → Genie Agent on metric views (12/12 benchmark)
 → Databricks App (AppKit, Altura-themed): Portfolio · Launch · Action Center · Mitigation Advisor · Ask the Data
```
Detailed diagram and asset map: **[docs/architecture.md](docs/architecture.md)**.

## 4 · Execution evidence (text, committed)
| Stage | Evidence |
|---|---|
| Synthetic source extracts landed | [`notebooks/01_generate_and_land_raw_data.ipynb`](notebooks/01_generate_and_land_raw_data.ipynb) |
| UC governance, metric views, ABAC persona proof, lineage | [`notebooks/02_unity_catalog_governance.ipynb`](notebooks/02_unity_catalog_governance.ipynb) |
| Model training, holdout metrics, SHAP, $ back-test, UC promotion | [`notebooks/03_train_models.ipynb`](notebooks/03_train_models.ipynb) |
| Scoring of the active pipeline with committed actions, explanations | [`notebooks/04_score_launches.ipynb`](notebooks/04_score_launches.ipynb) |
| Lakebase OLTP schema, seeds, Lakehouse Sync, synced tables | [`notebooks/05_lakebase_setup.ipynb`](notebooks/05_lakebase_setup.ipynb) |
| GenAI briefs + quality gate | [`notebooks/06_genai_launch_briefs.ipynb`](notebooks/06_genai_launch_briefs.ipynb) |
| Genie Agent + native benchmark eval + live Q&A | [`notebooks/07_genie_agent.ipynb`](notebooks/07_genie_agent.ipynb), [`evidence/genie_benchmarks.md`](evidence/genie_benchmarks.md) |
| Agent evaluation, UC registration, serving, endpoint answer | [`notebooks/08_mitigation_advisor_agent.ipynb`](notebooks/08_mitigation_advisor_agent.ipynb), [`evidence/agent_eval.md`](evidence/agent_eval.md) |
| **Closed loop**: app write → Lakebase → Lakehouse Sync → triggered re-score → app | [`notebooks/09_closed_loop_proof.ipynb`](notebooks/09_closed_loop_proof.ipynb) |
| Orchestrated job run (serverless) | [`evidence/job_run_daily_refresh.json`](evidence/job_run_daily_refresh.json) |
| App API against live Lakebase / Model Serving | [`evidence/app_api_smoke.md`](evidence/app_api_smoke.md) |
| Deployed app tested in the browser as a signed-in user: defects found and fixed, hover/layout/theme checks | [`evidence/app_ui_test.md`](evidence/app_ui_test.md) |

**Presentation deck:** [`docs/deck.pdf`](docs/deck.pdf) · talk track for the live demo: [`docs/demo_talk_track.md`](docs/demo_talk_track.md).

## 5 · Decisions & trade-offs
See **[docs/decisions_and_tradeoffs.md](docs/decisions_and_tradeoffs.md)**. Highlights:
- Features are computed *as of G3*, with a temporal holdout.
- A two-stage yield → risk model.
- One shared feature module for training, scoring, the agent's what-if tool and the app.
- Mitigations are modeled as auditable feature effects.
- Lakebase handles serving and writes, with Lakehouse Sync and an event-driven re-score.
- GPT-5.5 for strict-schema batch briefs; Claude for the interactive tool-calling agent.
- On-behalf-of-user auth so UC ABAC applies to AI answers.
- A human approves every action.

## 6 · Value
**[docs/value_model.md](docs/value_model.md)** covers buyer KPIs, cost of the problem, the back-test, sensitivity, run cost and time to value.

## 7 · AI tools & workflow
**[docs/ai_workflow.md](docs/ai_workflow.md)**: Claude Code with Databricks AI Dev Kit skills, FEVM MCP, and Databricks Connect so notebooks execute locally and commit their outputs. It also covers the bugs the AI caught and fixed, and the prompt patterns.

## 8 · Run it
```bash
# 0. local env (serverless v5 parity) and auth
databricks environments setup-local --profile <PROFILE> --serverless-version 5
# 1. data platform bundle: pipeline + jobs
./tools/bundle.sh deploy && ./tools/bundle.sh run npi_ingest
# 2. notebooks in order (each writes its outputs into the .ipynb)
./tools/run_notebook.sh notebooks/0{1,3,4,6,5,2,7,8}_*.py
# 3. app bundle
cd npi-control-tower && databricks bundle deploy && cd .. && uv run python tools/grant_app_access.py
# 4. prove the loop
./tools/run_notebook.sh notebooks/09_closed_loop_proof.py
```

## 9 · Repo map
```
databricks.yml, resources/        DAB: SDP pipeline, Lakeflow Jobs (daily, rescore-on-action trigger, retrain)
src/pipelines/npi_ingest/          Lakeflow SDP SQL (bronze/silver/gold)
src/npi/                           datagen.py (synthetic source systems), features.py (shared), agent.py (Mitigation Advisor)
src/sql/metric_views.sql           UC metric views
notebooks/                         01-09 (jupytext .py source + executed .ipynb with outputs)
npi-control-tower/                 Databricks App (AppKit: React client + Express server, own bundle)
evidence/                          run records, benchmark + eval results
docs/                              deck (PDF) + talk track, architecture, decisions, value model, AI workflow
tools/                             notebook runner, bundle wrapper, app grants
```
