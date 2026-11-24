# %% [markdown]
# # 06 · GenAI launch-readiness briefs (`ai_query` + MLflow Prompt Registry)
#
# For every active launch, an LLM (Databricks Foundation Model API, `databricks-gpt-5-5` - chosen for strict JSON-schema structured output)
# turns the model score, drivers and component readiness into the **one-page brief a G4 steering
# committee reads**: headline, situation, business impact and 2-3 recommended mitigations chosen
# *only* from the governed mitigation playbook (so every recommendation is executable in the app
# and quantifiable by the scoring model).
#
# * Runs as batch SQL inside the lakehouse (`ai_query` with a JSON-schema `responseFormat`), so it
#   is governed, logged and costs a few cents per run.
# * The prompt is versioned in the **MLflow Prompt Registry** (Unity Catalog) - prompt changes are
#   auditable like code.
# * Output `gold_launch_briefs` is synced to Lakebase for the app.

# %%
import os, sys, json
sys.path.insert(0, os.path.abspath("../src"))
import mlflow
from npi.env import FQ, get_spark, widget

spark = get_spark()
LLM = widget("brief_llm_endpoint", "databricks-gpt-5-5")   # strict JSON-schema output (Claude on FMAPI rejects forced tool use)
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")

PROMPT = """You are the supply-chain launch-readiness analyst for Altura Bonding & Tapes.
Write a concise brief for the NPI steering committee about ONE product launch moving from pilot to production.
Audience: business-unit president and supply-chain VP. Be specific, quantitative, and plain-spoken. No hype.

LAUNCH: {{launch}}
MODEL RISK DRIVERS (ranked): {{drivers}}
BOM COMPONENT READINESS AT PREDICTED PRODUCTION YIELD: {{components}}
ALLOWED MITIGATION ACTION TYPES (choose only from these): {{playbook}}

Rules:
- Use the numbers given; do not invent suppliers, dates, or costs.
- Recommended actions must use an allowed action_type and name the target component when relevant (material_id), or null for launch-level actions.
- Recommend at most 3 actions, highest expected risk reduction first.
- If risk is LOW, say so briefly and recommend at most one watch item.
"""
try:
    pr = mlflow.genai.register_prompt(name=f"{FQ}.launch_brief_prompt", template=PROMPT,
                                      commit_message="Launch-readiness steering-committee brief")
    print(f"Prompt registered: {pr.name} v{pr.version}")
except Exception as e:
    print(f"Prompt registry unavailable ({type(e).__name__}); using inline prompt")

SCHEMA = {"type": "json_schema", "json_schema": {"name": "launch_brief", "strict": True, "schema": {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "situation", "business_impact", "recommended_actions", "supplier_questions"],
    "properties": {
        "headline": {"type": "string"},
        "situation": {"type": "string"},
        "business_impact": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["action_type", "material_id", "title", "why"],
            "properties": {"action_type": {"type": "string"}, "material_id": {"type": ["string", "null"]},
                           "title": {"type": "string"}, "why": {"type": "string"}}}},
        "supplier_questions": {"type": "array", "items": {"type": "string"}}}}}}

# %%
playbook = json.dumps([r.asDict() for r in spark.table(f"{FQ}.silver_mitigation_playbook").select("action_type", "description").collect()])
spark.sql(f"""
CREATE OR REPLACE TEMPORARY VIEW brief_inputs AS
SELECT r.npi_id, r.risk_tier, r.risk_score, r.scored_at,
  to_json(named_struct('npi_id', r.npi_id, 'product', r.product_name, 'oem', r.oem_customer, 'program', r.oem_program,
     'sop_date', r.sop_date, 'weeks_to_sop', r.weeks_to_sop, 'risk_score', round(r.risk_score, 2), 'risk_tier', r.risk_tier,
     'year1_revenue_usd', r.year1_revenue_usd, 'revenue_at_risk_usd', r.revenue_at_risk_usd,
     'oem_platform_value_at_risk_usd', r.platform_value_at_risk_usd, 'pilot_yield_pct', r.pilot_yield_pct,
     'predicted_production_yield_pct', round(r.predicted_yield_pct, 1), 'yield_basis', r.yield_basis,
     'production_line', r.production_line, 'line_utilization_at_sop', r.planned_line_utilization)) AS launch_json,
  r.top_drivers_json,
  (SELECT to_json(collect_list(named_struct('material_id', c.material_id, 'component', c.material_desc,
          'status', c.readiness_status, 'coverage_at_predicted_yield', c.coverage_at_predicted_yield,
          'weekly_shortfall_at_peak', c.weekly_shortfall_at_peak, 'uom', c.uom, 'material_gap_weeks', c.material_gap_weeks,
          'sources', c.sources, 'lead_time_weeks', c.lead_time_weeks)))
   FROM {FQ}.gold_component_readiness c WHERE c.npi_id = r.npi_id AND c.readiness_status <> 'GREEN') AS components_json
FROM {FQ}.gold_launch_risk_scores r""")
prompt_sql = PROMPT.replace("'", "''")
briefs = spark.sql(f"""
SELECT npi_id, risk_tier, scored_at AS score_scored_at, resp,
       from_json(resp, 'headline STRING, situation STRING, business_impact STRING,
                 recommended_actions ARRAY<STRUCT<action_type STRING, material_id STRING, title STRING, why STRING>>,
                 supplier_questions ARRAY<STRING>') AS b
FROM (SELECT *, ai_query('{LLM}',
        replace(replace(replace(replace('{prompt_sql}', '{{{{launch}}}}', launch_json), '{{{{drivers}}}}', top_drivers_json),
                '{{{{components}}}}', coalesce(components_json, '[]')), '{{{{playbook}}}}', '{playbook.replace("'", "''")}'),
        responseFormat => '{json.dumps(SCHEMA)}') AS resp
      FROM brief_inputs)""")
briefs.createOrReplaceTempView("briefs_raw")
out = spark.sql(f"""
SELECT npi_id, risk_tier, b.headline, b.situation, b.business_impact,
       to_json(b.recommended_actions) AS recommended_actions_json, to_json(b.supplier_questions) AS supplier_questions_json,
       '{LLM}' AS llm_endpoint, score_scored_at, current_timestamp() AS generated_at
FROM briefs_raw""")
out.createOrReplaceTempView("v_briefs")
tbl = f"{FQ}.gold_launch_briefs"
if not spark.catalog.tableExists(tbl):
    spark.sql(f"""CREATE TABLE {tbl} COMMENT 'LLM-generated steering-committee brief per active launch (ai_query, structured output, playbook-constrained actions). Grain: npi_id.'
                  TBLPROPERTIES (delta.enableChangeDataFeed = true) AS SELECT * FROM v_briefs""")
    spark.sql(f"ALTER TABLE {tbl} ALTER COLUMN npi_id SET NOT NULL")
else:
    spark.sql(f"INSERT OVERWRITE TABLE {tbl} SELECT * FROM v_briefs")
print(f"{tbl}: {spark.table(tbl).count()} briefs")

# %% [markdown]
# ### Quality gate: recommendations must be executable playbook actions

# %%
chk = spark.sql(f"""
SELECT count(*) AS actions,
       sum(CASE WHEN a.action_type IN (SELECT action_type FROM {FQ}.silver_mitigation_playbook) THEN 1 ELSE 0 END) AS valid_type,
       sum(CASE WHEN a.material_id IS NULL OR a.material_id IN (SELECT material_id FROM {FQ}.gold_component_readiness c WHERE c.npi_id = b.npi_id) THEN 1 ELSE 0 END) AS valid_target
FROM {tbl} b LATERAL VIEW explode(from_json(recommended_actions_json, 'ARRAY<STRUCT<action_type STRING, material_id STRING, title STRING, why STRING>>')) t AS a""").first()
print(f"recommended actions: {chk.actions} | valid action_type: {chk.valid_type} | valid component target: {chk.valid_target}")

# %%
h = spark.table(tbl).where("npi_id = 'NPI-2027-014'").first()
print("HEADLINE:", h.headline, "\n\nSITUATION:", h.situation, "\n\nIMPACT:", h.business_impact)
for a in json.loads(h.recommended_actions_json):
    print(f"\n- [{a['action_type']}] {a['title']} ({a.get('material_id') or 'launch-level'})\n  why: {a['why']}")
print("\nSUPPLIER QUESTIONS:", *json.loads(h.supplier_questions_json), sep="\n- ")
