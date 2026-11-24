# %% [markdown]
# # 02 · Unity Catalog governance
#
# Everything in the Control Tower is governed in one place — Unity Catalog — across raw files,
# Delta tables, ML models, the LLM prompt, metric views, the Genie Agent and the Lakebase database
# (registered as catalog `npi_ops_lakebase`).
#
# | Control | What it does here |
# |---|---|
# | **Discovery & semantics** | Table/column comments, domain tags, `system.certification_status=certified` on gold, PK/FK constraints |
# | **Governed metrics** | UC metric views (`*_metrics`) - one definition of *Revenue at Risk* for Genie, the app and BI |
# | **ABAC column masking** | Supplier commercial terms (`unit_price`, `standard_cost`) tagged `masking_rule=redact` -> one schema-level policy masks them for everyone without the PROCUREMENT persona |
# | **ABAC row filtering** | Region columns tagged `rls_filter_key` -> regional planners only see launches for their region |
# | **Lineage & audit** | Automatic column-level lineage from landing files to the app's serving tables; access audit in system tables |
#
# Personas are resolved from an **entitlements table** (instant toggle, no group-cache delays). In
# production these map to Altura's IdP groups (e.g. `btd-procurement`, `btd-emea-planning`).
# *Trade-off:* this shared demo account has hit its governed-tag quota, so two existing generic
# governed tags are reused; at Altura we would create `btd_data_class` / `btd_region_scope`.

# %%
import os, sys
sys.path.insert(0, os.path.abspath("../src"))
import pandas as pd
from npi.env import CATALOG, SCHEMA, FQ, get_spark

spark = get_spark()
me = spark.sql("SELECT current_user()").first()[0]
def sql(q, show=False):
    df = spark.sql(q)
    if show:
        print(df.toPandas().to_string(index=False))
        return None
    return df
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 90)

# %% [markdown]
# ## 1 · Discovery: schema/table tags, certification, comments, constraints

# %%
# governed keys (business_unit, domain, layer) use their allowed values; free-form keys carry the specifics
_ = sql(f"ALTER SCHEMA {FQ} SET TAGS ('business_unit' = 'Operations', 'domain' = 'supply_chain', "
    f"'business_division' = 'Bonding & Tapes', 'npi_use_case' = 'launch_readiness', 'data_origin' = 'synthetic')")
tables = [r.tableName for r in sql(f"SHOW TABLES IN {FQ}").collect() if not r.isTemporary]
layer = lambda t: ("bronze" if t.startswith("bronze_") else "silver" if t.startswith("silver_") else
                   "gold" if t.startswith("gold_") else "operational_cdc" if t.startswith("lb_") else "semantic")
source = {"sap": "SAP ECC", "mes": "MES", "plm": "PLM", "oem": "OEM EDI", "mfg": "Mfg Engineering", "launch_outcomes": "Commercial"}
for t in tables:
    if t.endswith("_metrics"):
        continue
    lyr = layer(t)
    tags = f"'layer' = '{lyr}'" if lyr in ("bronze", "silver", "gold") else f"'npi_layer' = '{lyr}'"
    src = next((v for k, v in source.items() if k in t), None)
    if src:
        tags += f", 'npi_source_system' = '{src}'"
    for kind in ("TABLE", "MATERIALIZED VIEW", "STREAMING TABLE"):
        try:
            sql(f"ALTER {kind} {FQ}.{t} SET TAGS ({tags})"); break
        except Exception:
            continue
for t in ["gold_launch_risk_scores", "gold_component_readiness", "gold_ramp_supply_curve", "gold_launch_briefs"]:
    sql(f"ALTER TABLE {FQ}.{t} SET TAGS ('system.certification_status' = 'certified')")
print(f"tagged {len(tables)} objects in {FQ}")

# %%
COLS = {
 "gold_launch_risk_scores": {
   "npi_id": "NPI launch identifier (PLM)", "risk_score": "Probability (0-1) that the launch ramp fails: slips >2 weeks or first-90-day OTIF <85%. Includes committed mitigations.",
   "baseline_risk_score": "Risk score before any committed mitigation actions", "risk_tier": "HIGH >= 0.60, MEDIUM 0.25-0.60, LOW < 0.25",
   "revenue_at_risk_usd": "risk_score x year-1 revenue (USD)", "platform_value_at_risk_usd": "risk_score x P(platform lost | failed ramp) x OEM program lifetime value (auto/EV only)",
   "predicted_yield_pct": "Predicted first-12-week production yield (%) from yield model blended with production-trial runs",
   "predicted_yield_gap_pts": "Pilot yield minus predicted production yield (percentage points)",
   "min_coverage_at_predicted_yield": "Lowest BOM component coverage = qualified weekly capacity / ramp-peak need at predicted yield",
   "worst_material_gap_weeks": "Max over novel components of (lead time + PPAP wait) - (weeks to SOP - 8); >0 means material cannot arrive for build-ahead",
   "binding_component_desc": "BOM component with the lowest supply coverage (the bottleneck)", "top_drivers_json": "Top actionable risk drivers with model contribution and plain-language detail (JSON)",
   "actions_applied": "Number of committed mitigation actions (from Lakebase) reflected in the score", "sop_date": "Start of production date agreed with the OEM"},
 "gold_component_readiness": {
   "coverage_at_predicted_yield": "Qualified capacity available to this launch / ramp-peak weekly need at predicted production yield",
   "coverage_at_pilot_yield": "Same coverage computed at pilot yield - how ramp plans are built today",
   "weekly_shortfall_at_peak": "Units per week short at ramp peak (uom column)", "readiness_status": "RED / AMBER / GREEN component readiness",
   "n_sources_qualified_by_peak": "Suppliers with PPAP approval planned on or before the ramp peak (SOP + 8 weeks)", "material_gap_weeks": "Weeks the material arrives too late for build-ahead (novel materials)"},
}
# idempotent: only touch columns whose comment differs. (Schema-metadata changes on a table that a Lakebase
# synced table streams from force a full re-sync, so re-runs must be no-ops.)
for t, cols in COLS.items():
    current = {r.col_name: r.comment for r in spark.sql(f"DESCRIBE TABLE {FQ}.{t}").collect()}
    for c, txt in cols.items():
        if current.get(c) != txt:
            sql(f"ALTER TABLE {FQ}.{t} ALTER COLUMN {c} COMMENT '{txt}'")
for stmt in [f"ALTER TABLE {FQ}.gold_launch_risk_scores ADD CONSTRAINT pk_launch_risk PRIMARY KEY (npi_id)",
             f"ALTER TABLE {FQ}.gold_component_readiness ADD CONSTRAINT pk_component_readiness PRIMARY KEY (npi_id, material_id)",
             f"ALTER TABLE {FQ}.gold_component_readiness ADD CONSTRAINT fk_component_launch FOREIGN KEY (npi_id) REFERENCES {FQ}.gold_launch_risk_scores",
             f"ALTER TABLE {FQ}.gold_launch_briefs ADD CONSTRAINT fk_brief_launch FOREIGN KEY (npi_id) REFERENCES {FQ}.gold_launch_risk_scores"]:
    try:
        sql(stmt)
    except Exception as e:
        print("skip:", str(e).split("\n")[0][:110])
print("comments + constraints applied")

# %% [markdown]
# ## 2 · Governed metrics: UC metric views

# %%
mv_sql = open("../src/sql/metric_views.sql").read().replace("${catalog}", CATALOG).replace("${schema}", SCHEMA)
for stmt in [s.strip() for s in mv_sql.split("$$;") if "CREATE" in s]:
    stmt = stmt[stmt.index("CREATE"):] + "$$"
    sql(stmt)
    print("created", stmt.split("VIEW ")[1].split()[0])
sql(f"""SELECT `Risk Tier`, MEASURE(`Active Launches`) launches, ROUND(MEASURE(`Revenue at Risk`)/1e6, 1) revenue_at_risk_musd,
        ROUND(MEASURE(`OEM Platform Value at Risk`)/1e6, 1) platform_value_at_risk_musd
        FROM {FQ}.npi_launch_readiness_metrics GROUP BY ALL ORDER BY 1""", show=True)
sql(f"""SELECT `SOP Year`, MEASURE(`Launches`) launches, ROUND(MEASURE(`Ramp Failure Rate`), 3) failure_rate,
        MEASURE(`OEM Platforms Lost`) platforms_lost, ROUND(MEASURE(`Expedite Cost`)/1e6, 1) expedite_musd
        FROM {FQ}.npi_launch_history_metrics GROUP BY ALL ORDER BY 1""", show=True)

# %% [markdown]
# ## 3 · Fine-grained access: persona entitlements + ABAC policies

# %%
sql(f"""CREATE TABLE IF NOT EXISTS {FQ}.npi_user_entitlements (
          user_email STRING NOT NULL, persona STRING NOT NULL, region_scope STRING NOT NULL, can_view_commercial_terms BOOLEAN NOT NULL)
        COMMENT 'Persona entitlements for the Control Tower (maps to IdP groups in production). region_scope = ALL | NA | EMEA | APAC'""")
sql(f"""MERGE INTO {FQ}.npi_user_entitlements t
        USING (SELECT '{me}' user_email, 'GLOBAL_SUPPLY_CHAIN' persona, 'ALL' region_scope, true can_view_commercial_terms) s
        ON t.user_email = s.user_email WHEN NOT MATCHED THEN INSERT *""")
sql(f"""CREATE OR REPLACE FUNCTION {FQ}.npi_can_view_commercial() RETURNS BOOLEAN
        COMMENT 'TRUE if caller may see supplier commercial terms (prices). Unlisted principals (e.g. service principals) are denied.'
        RETURN coalesce((SELECT max(can_view_commercial_terms) FROM {FQ}.npi_user_entitlements WHERE user_email = current_user()), false)""")
sql(f"""CREATE OR REPLACE FUNCTION {FQ}.npi_region_scope() RETURNS STRING
        COMMENT 'Region scope of the caller (ALL/NA/EMEA/APAC). Unlisted principals default to ALL for pipeline and job identities.'
        RETURN coalesce((SELECT max(region_scope) FROM {FQ}.npi_user_entitlements WHERE user_email = current_user()), 'ALL')""")
sql(f"""CREATE OR REPLACE FUNCTION {FQ}.npi_redact_commercial(v DOUBLE) RETURNS DOUBLE
        COMMENT 'ABAC mask: supplier commercial terms visible only to procurement / global supply chain personas'
        RETURN CASE WHEN {FQ}.npi_can_view_commercial() THEN v ELSE NULL END""")
sql(f"""CREATE OR REPLACE FUNCTION {FQ}.npi_region_filter(region STRING) RETURNS BOOLEAN
        COMMENT 'ABAC row filter: regional planners see only their region'
        RETURN {FQ}.npi_region_scope() = 'ALL' OR region = {FQ}.npi_region_scope()""")

# tag the sensitive / scoping columns (governed tags drive the policies)
for t, c in [("silver_supplier_qualification", "unit_price"), ("silver_materials", "standard_cost")]:
    sql(f"ALTER MATERIALIZED VIEW {FQ}.{t} ALTER COLUMN {c} SET TAGS ('masking_rule' = 'redact')")
sql(f"ALTER MATERIALIZED VIEW {FQ}.gold_launch_portfolio ALTER COLUMN region SET TAGS ('rls_filter_key')")
sql(f"ALTER MATERIALIZED VIEW {FQ}.silver_coating_lines ALTER COLUMN region SET TAGS ('rls_filter_key')")

sql(f"""CREATE OR REPLACE POLICY npi_mask_commercial_terms ON SCHEMA {FQ}
        COMMENT 'Mask supplier commercial terms (columns tagged masking_rule=redact) unless persona may view them'
        COLUMN MASK {FQ}.npi_redact_commercial TO `account users` FOR TABLES
        MATCH COLUMNS has_tag_value('masking_rule', 'redact') AS c ON COLUMN c""")
sql(f"""CREATE OR REPLACE POLICY npi_region_row_filter ON SCHEMA {FQ}
        COMMENT 'Regional planners only see rows for their region (columns tagged rls_filter_key)'
        ROW FILTER {FQ}.npi_region_filter TO `account users` FOR TABLES
        MATCH COLUMNS has_tag('rls_filter_key') AS r USING COLUMNS (r)""")
sql(f"SHOW POLICIES ON SCHEMA {FQ}", show=True)

# %% [markdown]
# ### Prove it: same query, two personas (toggle, verify, restore)

# %%
probe = f"""SELECT (SELECT count(*) FROM {FQ}.gold_launch_portfolio) AS launches_visible,
                   (SELECT count(DISTINCT region) FROM {FQ}.gold_launch_portfolio) AS regions_visible,
                   (SELECT round(avg(unit_price), 2) FROM {FQ}.silver_supplier_qualification) AS avg_supplier_unit_price"""
print("Persona GLOBAL_SUPPLY_CHAIN (procurement rights):"); sql(probe, show=True)
sql(f"UPDATE {FQ}.npi_user_entitlements SET persona='EMEA_PLANNER', region_scope='EMEA', can_view_commercial_terms=false WHERE user_email='{me}'")
print("Persona EMEA_PLANNER:"); sql(probe, show=True)
sql(f"UPDATE {FQ}.npi_user_entitlements SET persona='GLOBAL_SUPPLY_CHAIN', region_scope='ALL', can_view_commercial_terms=true WHERE user_email='{me}'")
print("Restored:"); sql(probe, show=True)

# %% [markdown]
# ## 4 · Lineage: from SAP/MES landing files to the app's serving tables

# %%
sql(f"""SELECT source_table_full_name AS source, target_table_full_name AS target, count(*) AS events
        FROM system.access.table_lineage
        WHERE target_table_catalog = '{CATALOG}' AND target_table_schema = '{SCHEMA}' AND event_date >= current_date() - 7
          AND source_table_full_name IS NOT NULL
        GROUP BY ALL ORDER BY target, source""", show=True)
