# %% [markdown]
# # 07 · Genie Agent: "Ask the Launch Readiness Control Tower"
#
# A curated Genie Agent so a supply-chain VP, NPI manager or buyer can ask questions in plain English
# ("Which Q1 launches are single-sourced?", "What did yield gaps cost us last year?") and get governed
# answers. It is built on the **UC metric views** (one definition of every KPI) plus a few detail tables,
# carries business instructions + example SQL, and is **benchmarked** with Genie's native evaluation.
# Genie runs on-behalf-of the user, so the UC ABAC masks / row filters from notebook 02 apply.

# %%
import os, sys, json, time, hashlib
sys.path.insert(0, os.path.abspath("../src"))
import pandas as pd
from npi.env import FQ, get_spark, get_ws, widget

spark, w = get_spark(), get_ws()
WAREHOUSE = widget("warehouse_id", "ab67079061fe959d")
TITLE = "Altura BTD - NPI Launch Readiness"
me = w.current_user.me().user_name
hid = lambda s: hashlib.md5(s.encode()).hexdigest()   # deterministic 32-hex ids -> idempotent updates

# current state of mitigation actions (latest CDC image from Lakebase via Lakehouse Sync)
spark.sql(f"""CREATE OR REPLACE VIEW {FQ}.v_mitigation_actions_current
  COMMENT 'Current state of mitigation actions committed in the Control Tower app (Lakebase ops.mitigation_actions via Lakehouse Sync CDC)'
  AS SELECT action_id, npi_id, material_id, action_type, title, status, owner, due_date, estimated_cost_usd, source,
            created_by, created_at, updated_at
     FROM (SELECT *, row_number() OVER (PARTITION BY action_id ORDER BY _sort_by DESC) rn
           FROM {FQ}.lb_mitigation_actions_history WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete'))
     WHERE rn = 1 AND _pg_change_type <> 'delete'""")
print("view ready:", f"{FQ}.v_mitigation_actions_current")

# %%
M_LR, M_CS, M_HI = f"{FQ}.npi_launch_readiness_metrics", f"{FQ}.npi_component_supply_metrics", f"{FQ}.npi_launch_history_metrics"
INSTRUCTIONS = [
  "Context: Altura Industries' Bonding & Tapes Division (BTD). New product introductions (NPIs) that passed pilot (gate G3) are being scaled to production for OEM programs. Today's evaluation date is 2026-11-23; all data is synthetic.",
  f"Active pipeline KPIs (risk, revenue at risk, OEM platform value at risk, yield gap, shortfall): use metric view {M_LR} with MEASURE(). Component / material / supplier-capacity questions: use {M_CS}. Historical launch outcomes 2020-2026 (failure rate, slip, OTIF, expedite, E&O, lost platforms, root causes): use {M_HI}.",
  "Metric views must be queried with MEASURE(`Measure Name`) and GROUP BY ALL; never SUM a measure directly. Backtick-quote names that contain spaces.",
  "Risk score = probability the launch ramp fails (slips > 2 weeks or first-90-day OTIF < 85%). Risk tiers: HIGH >= 60%, MEDIUM 25-60%, LOW < 25%. 'At risk' means Risk Tier = 'HIGH' unless the user says otherwise.",
  "Revenue at risk = risk score x year-1 revenue. OEM platform value at risk = risk x P(platform lost | failed ramp) x OEM program lifetime value (auto/EV only). In SQL, return money measures as USD straight from MEASURE() (do not divide or round); in the answer text, state them in $M with one decimal.",
  "Readiness status of a component: RED = qualified supply covers < 90% of ramp-peak need at predicted production yield, or material arrives > 2 weeks too late for build-ahead, or no supplier qualified by the ramp peak (SOP + 8 weeks). 'Single-sourced' = at most one supplier qualified by the ramp peak.",
  "Pilot-to-production yield gap = pilot yield minus (predicted or realized) production yield, in percentage points. Ramp plans today assume pilot yield.",
  f"Supplier qualification (PPAP) status and dates per material and supplier are in {FQ}.silver_supplier_qualification joined to {FQ}.silver_suppliers on supplier_id. unit_price is commercially confidential and may be masked (NULL) for some users - say so if it is NULL.",
  f"Mitigation actions (who is doing what, status) are in {FQ}.v_mitigation_actions_current; committed = status IN ('APPROVED','IN_PROGRESS','DONE'). LLM steering-committee briefs per launch are in {FQ}.gold_launch_briefs.",
  "When asked 'which launch' or 'which launches', always return `Launch ID`, `Product` and the measure being ranked or filtered on; for top-N questions ORDER BY that measure DESC and LIMIT N.",
  "'AFT-7200' is the structural battery-enclosure foam tape for Northstar Motors program NSM-EVX9 (Launch ID NPI-2027-014). Quarters: Q1 2027 = SOP Quarter '2027-Q1'.",
]
EXAMPLES = [
  ("Show revenue at risk and high-risk launches by OEM customer",
   f"SELECT `OEM Customer`, MEASURE(`High-Risk Launches`) AS high_risk_launches, MEASURE(`Revenue at Risk`) AS revenue_at_risk_usd FROM {M_LR} GROUP BY ALL ORDER BY revenue_at_risk_usd DESC"),
  ("Which components are red for a given launch?",
   f"SELECT `Component`, `Material Category`, `Approved Sources`, MEASURE(`Average Coverage at Predicted Yield`) AS coverage, MEASURE(`Worst Material Gap (weeks)`) AS gap_weeks FROM {M_CS} WHERE `Product Code` = 'AFT-7200' AND `Readiness Status` = 'RED' GROUP BY ALL ORDER BY coverage"),
  ("What was the ramp failure rate by product family historically?",
   f"SELECT `Product Family`, MEASURE(`Launches`) AS launches, ROUND(MEASURE(`Ramp Failure Rate`), 3) AS failure_rate FROM {M_HI} GROUP BY ALL ORDER BY failure_rate DESC"),
  ("Which suppliers are still in PPAP for AFT-7200 components?",
   f"SELECT s.supplier_name, q.material_id, q.qualification_status, q.ppap_planned_date FROM {FQ}.silver_supplier_qualification q JOIN {FQ}.silver_suppliers s ON s.supplier_id = q.supplier_id WHERE q.material_id IN (SELECT material_id FROM {FQ}.gold_component_readiness WHERE product_code = 'AFT-7200') AND q.qualification_status <> 'QUALIFIED' ORDER BY q.ppap_planned_date"),
]
SAMPLES = ["Which high-risk launches have SOP in Q1 2027, and what is their bottleneck material?",
           "How much revenue and OEM platform value is at risk by customer?",
           "Why is AFT-7200 at risk?",
           "What did failed ramps cost us in expedites and E&O by year?",
           "Which root causes drive most failed ramps?",
           "Which mitigation actions are in progress and who owns them?"]
BENCH = [
  ("How many active launches are high risk?", f"SELECT MEASURE(`High-Risk Launches`) AS high_risk_launches FROM {M_LR}"),
  ("What is the total revenue at risk across the active launch pipeline?", f"SELECT MEASURE(`Revenue at Risk`) AS revenue_at_risk FROM {M_LR}"),
  ("Which launch has the highest revenue at risk?", f"SELECT `Launch ID`, `Product`, MEASURE(`Revenue at Risk`) AS revenue_at_risk FROM {M_LR} GROUP BY ALL ORDER BY revenue_at_risk DESC LIMIT 1"),
  ("Revenue at risk by OEM customer", f"SELECT `OEM Customer`, MEASURE(`Revenue at Risk`) AS revenue_at_risk FROM {M_LR} GROUP BY ALL ORDER BY revenue_at_risk DESC"),
  ("List the high-risk launches with SOP in Q1 2027", f"SELECT `Launch ID`, `Product` FROM {M_LR} WHERE `Risk Tier` = 'HIGH' AND `SOP Quarter` = '2027-Q1' GROUP BY ALL ORDER BY `Launch ID`"),
  ("Which BOM components of AFT-7200 are RED?", f"SELECT `Component` FROM {M_CS} WHERE `Product Code` = 'AFT-7200' AND `Readiness Status` = 'RED' GROUP BY ALL ORDER BY `Component`"),
  ("How many components across the active pipeline have no supplier qualified by the ramp peak?", f"SELECT MEASURE(`Components Without Qualified Source`) AS n FROM {M_CS}"),
  ("What was the historical ramp failure rate by SOP year?", f"SELECT `SOP Year`, MEASURE(`Ramp Failure Rate`) AS failure_rate FROM {M_HI} GROUP BY ALL ORDER BY `SOP Year`"),
  ("How many OEM platforms did we lose and what was their lifetime value?", f"SELECT MEASURE(`OEM Platforms Lost`) AS platforms_lost, MEASURE(`Lost Platform Lifetime Value`) AS lifetime_value FROM {M_HI}"),
  ("What is the most common root cause of failed ramps?", f"SELECT `Root Cause`, MEASURE(`Failed Ramps`) AS failed_ramps FROM {M_HI} WHERE `Root Cause` <> 'None - launched on plan' GROUP BY ALL ORDER BY failed_ramps DESC LIMIT 1"),
  ("Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch", f"SELECT `Pilot-to-Line Technology Mismatch`, MEASURE(`Average Pilot-to-Production Yield Gap (pts)`) AS yield_gap FROM {M_HI} GROUP BY ALL ORDER BY 1"),
  ("Which committed mitigation actions are there and for which launches?", f"SELECT npi_id, action_type, status, title FROM {FQ}.v_mitigation_actions_current WHERE status IN ('APPROVED','IN_PROGRESS','DONE') ORDER BY npi_id"),
]
for q, s in BENCH + [(q, s) for q, s in EXAMPLES]:
    spark.sql(s).limit(1).collect()     # every canonical SQL must execute
print(f"{len(BENCH)} benchmark + {len(EXAMPLES)} example SQLs validated")

# %%
def cc(col, desc=None, syn=None, match=False):
    d = {"column_name": col}
    if desc: d["description"] = [desc]
    if syn: d["synonyms"] = syn
    if match: d.update({"enable_entity_matching": True, "enable_format_assistance": True})
    return d

space = {
  "version": 2,
  "config": {"sample_questions": sorted([{"id": hid("s" + q), "question": [q]} for q in SAMPLES], key=lambda x: x["id"])},
  "data_sources": {
    "metric_views": sorted([
      {"identifier": M_LR, "column_configs": sorted([cc("OEM Customer", match=True), cc("Product Code", match=True), cc("Risk Tier", match=True), cc("Market Segment", match=True)], key=lambda c: c["column_name"])},
      {"identifier": M_CS, "column_configs": sorted([cc("Readiness Status", match=True), cc("Material Category", match=True), cc("Product Code", match=True)], key=lambda c: c["column_name"])},
      {"identifier": M_HI, "column_configs": sorted([cc("Root Cause", match=True), cc("Product Family", match=True)], key=lambda c: c["column_name"])},
    ], key=lambda x: x["identifier"]),
    "tables": sorted([
      {"identifier": f"{FQ}.gold_launch_briefs"},
      {"identifier": f"{FQ}.silver_supplier_qualification", "column_configs": [cc("qualification_status", match=True)]},
      {"identifier": f"{FQ}.silver_suppliers", "column_configs": [cc("supplier_name", match=True)]},
      {"identifier": f"{FQ}.v_mitigation_actions_current", "column_configs": sorted([cc("action_type", match=True), cc("status", match=True)], key=lambda c: c["column_name"])},
    ], key=lambda x: x["identifier"]),
  },
  "instructions": {
    "text_instructions": [{"id": hid("instructions-v2"), "content": INSTRUCTIONS}],
    "example_question_sqls": sorted([{"id": hid("e" + q), "question": [q], "sql": [s]} for q, s in EXAMPLES], key=lambda x: x["id"]),
  },
  "benchmarks": {"questions": sorted([{"id": hid("b" + q), "question": [q], "answer": [{"format": "SQL", "content": [s]}]} for q, s in BENCH], key=lambda x: x["id"])},
}
ser = json.dumps(space)
existing = [s for s in (w.genie.list_spaces().spaces or []) if s.title == TITLE]
if existing:
    sp = w.genie.update_space(existing[0].space_id, serialized_space=ser, warehouse_id=WAREHOUSE,
                              description="Governed NL Q&A over NPI launch readiness: risk, supply coverage, PPAP, yield gap, history.")
    SPACE_ID = existing[0].space_id; print("updated Genie Agent", SPACE_ID)
else:
    parent = f"/Workspace/Users/{me}/npi_launch_readiness_genie"   # (the MLflow experiment owns the plain name)
    w.workspace.mkdirs(parent)
    sp = w.genie.create_space(warehouse_id=WAREHOUSE, serialized_space=ser, title=TITLE, parent_path=parent,
                              description="Governed NL Q&A over NPI launch readiness: risk, supply coverage, PPAP, yield gap, history.")
    SPACE_ID = sp.space_id; print("created Genie Agent", SPACE_ID)
json.dump({"space_id": SPACE_ID, "title": TITLE}, open("../resources/genie_space.json", "w"), indent=2)
print(f"{w.config.host}/genie/rooms/{SPACE_ID}")

# %% [markdown]
# ## Benchmark evaluation (Genie native eval: generated SQL result vs. canonical SQL result)

# %%
run = w.genie.genie_create_eval_run(SPACE_ID)
rid = run.eval_run_id
for _ in range(120):
    r = w.genie.genie_get_eval_run(SPACE_ID, rid)
    if str(r.eval_run_status).endswith(("DONE", "FAILED", "CANCELLED")):
        break
    time.sleep(10)
print("eval run", rid, r.eval_run_status)
res = w.genie.genie_list_eval_results(SPACE_ID, rid).eval_results or []
rows = []
for x in res:
    d = w.genie.genie_get_eval_result_details(SPACE_ID, rid, x.result_id)
    a = d.assessment
    rows.append({"question": (x.question or [""])[0] if isinstance(x.question, list) else x.question,
                 "assessment": str(getattr(a, "value", a)).replace("GenieEvalAssessment.", ""),
                 "reasons": "; ".join(str(v) for v in (d.assessment_reasons or []))[:120]})
ev = pd.DataFrame(rows)
pd.set_option("display.max_colwidth", 80); pd.set_option("display.width", 250)
print(ev.to_string(index=False))
good = ev.assessment.str.contains("GOOD").sum()
print(f"\nBenchmark accuracy: {good}/{len(ev)} = {good/len(ev):.0%}")
with open("../evidence/genie_benchmarks.md", "a") as f:
    f.write(f"\n## Run {rid} ({time.strftime('%Y-%m-%d %H:%M')} UTC)\nAccuracy: **{good}/{len(ev)} = {good/len(ev):.0%}**\n\n"
            + ev.to_markdown(index=False) + "\n")

# %% [markdown]
# ## A live question, end to end

# %%
m = w.genie.start_conversation_and_wait(SPACE_ID, "Which high-risk launches have SOP in Q1 2027, and what is their bottleneck material and revenue at risk?")
for att in m.attachments or []:
    if att.text: print("ANSWER:", att.text.content)
    if att.query:
        print("SQL:", att.query.query)
        qr = w.genie.get_message_attachment_query_result(SPACE_ID, m.conversation_id, m.message_id, att.attachment_id)
        cols = [c.name for c in qr.statement_response.manifest.schema.columns]
        print(pd.DataFrame(qr.statement_response.result.data_array, columns=cols).to_string(index=False))
