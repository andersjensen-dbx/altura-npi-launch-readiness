# FE Bar submission: form answers (draft)

**Customer name:** Altura Industries (fictional customer)

**Industry / vertical:** Manufacturing (diversified industrial), Bonding & Tapes. Supply chain / new product introduction.

## What is the business challenge you are solving?
Altura is excellent at taking a new product through pilot, but it struggles to scale the supply chain from pilot to production.
- Ramp plans for new tapes are built on pilot assumptions: pilot-line yields (about 91%) and pilot-qualified, often single-source, new-to-Altura materials.
- On production lines, yield drops 10-20 points. The one qualified supplier for a novel foam core or liner can't cover the ramp peak, or a second source's PPAP lands after SOP.
- The signals sit in four disconnected systems: SAP (BOM, approved sources, POs), MES (yields), PLM (stage gates) and OEM EDI (demand). The problem surfaces late, as expedites, low OTIF and missed SOPs.

For OEM-specified EV and automotive tapes, a missed SOP doesn't just delay revenue: the OEM qualifies a competitor and Altura loses the platform for its 5-7 year life. In our synthetic BTD history, 32% of launches that passed pilot missed their ramp. That cost about $44M a year (margin view), and 22 OEM platforms were lost in 2020-26.

## How does your Databricks solution address this challenge?
The NPI Launch Readiness Control Tower is one integrated data journey:
1. **Lakeflow:** Spark Declarative Pipelines ingest SAP, MES, PLM and OEM EDI extracts with Auto Loader. Silver has data-quality expectations, an AUTO CDC SCD2 history of supplier qualifications (PPAP slips and capacity notices are auditable), and gold launch-by-component supply views.
2. **Unity Catalog:** governs it all: tags and certification, metric views as one definition of "revenue at risk", ABAC column masks on supplier prices and regional row filters, lineage from landing files to the app, and the models, prompt, Genie Agent and Lakebase catalog.
3. **ML:** MLflow models in the UC registry predict the pilot-to-production yield gap, then the probability of ramp failure. They are trained as of the G3 gate with a temporal holdout and explained per launch.
4. **GenAI:** `ai_query` writes steering-committee briefs per launch. The Mitigation Advisor, a tool-calling agent on Model Serving, runs on behalf of the user and simulates mitigation packages with the production models before recommending one. It is evaluated with MLflow (100% on tool-use, simulation, grounding, fact and guardrail scorers; 4.1/5 executive quality from an LLM judge; a release gate also re-runs the what-if on the packaged model exactly as Model Serving loads it).
5. **Lakebase:** serves scores to the app through synced tables. Its native Postgres tables record the mitigation actions managers approve, and Lakehouse Sync streams those back to Unity Catalog. A table-update trigger re-scores the launch, which closes the loop in minutes.
6. **Genie Agent:** built on the metric views, with a 12/12 benchmark score, for questions like "which Q1 launches are single-sourced?".
7. **Databricks App:** an Altura-themed AppKit app. It has a portfolio watchlist, a launch drill-down (drivers, ramp supply curve, BOM readiness, AI brief), an Action Center, the Mitigation Advisor, and Ask the Data.

## What AI tools did you use, and what was your workflow? What decisions and trade-offs did you make?
**Tools and workflow.** I used Claude Code as a pair-programmer and operator, with the Databricks AI Dev Kit skills (pipelines, DABs, jobs, Lakebase, apps and app design, Genie, metric views, synthetic data). The FEVM MCP handled the workspace and a short-lived metastore grant. Notebooks ran locally on serverless through Databricks Connect, so their outputs are committed as evidence. The workflow was:
- frame the problem with the AI,
- design a causal synthetic data contract,
- run a build → run → read → fix loop against the workspace,
- use evaluation as a release gate.

The AI caught and fixed real issues. One example: the risk score and the ramp chart used different definitions of qualified capacity; this was spotted from the rendered app and unified end to end. Others included synced-table schema drift, a structured-output limitation, and credential passthrough versus ABAC.

**Key trade-offs** (full list in `docs/decisions_and_tradeoffs.md`):
- Features are computed as of G3, with a temporal holdout, to avoid leakage.
- A two-stage yield-then-risk model makes the hidden yield multiplier actionable.
- One shared feature module for training, scoring and the agent's what-if tool avoids train/serve skew.
- Mitigations are modeled as auditable feature effects rather than learned causal effects.
- Lakebase handles serving and writes, with Lakehouse Sync and an event-driven re-score, giving minutes of latency at low cost.
- GPT-5.5 handles strict-schema batch briefs; Claude handles interactive tool use.
- The agent uses on-behalf-of-user auth so ABAC applies to AI answers.
- A human approves every action.
- Governed tags were reused because of the account quota.

## What are the business outcomes and impact?
**Back-test on 2025-26 launches:** flagging the top 30% riskiest launches at G3 catches 66% of failed ramps. Those launches carry 91% of total failure cost and 6 of 7 lost OEM platforms ($144M lifetime revenue). At a conservative 50% mitigation success rate, that is about **$19.8M a year of avoidable cost** (range $12-28M for 30-70% success), plus retained platforms. The run cost is well under $150K a year.

**Today's pipeline:** $57.3M of year-1 revenue is at risk across 36 launches before mitigation ($52.0M after the three in-flight actions), plus $57M of OEM platform value. The single largest exposure is AFT-7200 for Northstar Motors ($17.1M, 93% risk). Committing the Advisor's package moved it from 93% to 15% risk ($14.4M protected), reflected in the app 3.6 minutes later through Lakebase → Lakehouse Sync → event-triggered re-score.

**KPIs moved:** NPI revenue realization, launches on time to SOP, first-90-day OTIF, expedite and E&O spend, single-source exposure at SOP, and time from risk signal to committed mitigation.

**Executive sponsor:** Group President / Chief Supply Chain Officer. **Domain owner:** VP Supply Chain / NPI Commercialization, BTD.

**GitHub repo link:** https://github.com/andersjensen-dbx/altura-npi-launch-readiness

**Presentation deck:** [`docs/deck.pdf`](deck.pdf) (12 slides, outcome first, with a live-demo slot), talk track in [`docs/demo_talk_track.md`](demo_talk_track.md).
