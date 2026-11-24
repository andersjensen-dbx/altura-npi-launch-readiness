# %% [markdown]
# # 05 · Lakebase: operational serving + write-back (closed loop)
#
# Lakebase (serverless Postgres) is the **operational layer** of the Control Tower:
#
# | Direction | Mechanism | Objects |
# |---|---|---|
# | Lakehouse → app (read, ms latency) | **Lakebase synced tables** (managed Delta → Postgres sync, triggered after every scoring run) | `serving.launch_risk_scores`, `serving.component_readiness`, `serving.ramp_supply_curve`, `serving.launch_briefs`, `serving.launch_risk_history`, `serving.mitigation_playbook` |
# | App → OLTP (write, transactional) | Native Postgres tables owned by the app | `ops.mitigation_actions`, `ops.gate_signoffs` |
# | OLTP → lakehouse (CDC) | **Lakehouse Sync** (Postgres CDC → UC Delta SCD2 history) | `lb_mitigation_actions_history`, `lb_gate_signoffs_history` → read by the scoring job |
#
# That last hop closes the loop: a mitigation committed in the app changes the next risk score.
# Lakebase is also registered in Unity Catalog (`npi_ops_lakebase`) so it's governed and discoverable.

# %%
import os, sys, json, time
sys.path.insert(0, os.path.abspath("../src"))
import psycopg
from databricks.sdk.service.postgres import (SyncedTable, SyncedTableSyncedTableSpec as SyncedTableSpec, NewPipelineSpec,
    CdfConfig, SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy as Policy)
from npi.env import CATALOG, SCHEMA, FQ, get_spark, get_ws

w, spark = get_ws(), get_spark()
PROJECT, BRANCH = "npi-readiness", "production"
BR = f"projects/{PROJECT}/branches/{BRANCH}"
EP = f"{BR}/endpoints/primary"
LB_CATALOG = "npi_ops_lakebase"
SYNC_META_SCHEMA = "npi_lakebase_sync"
me = w.current_user.me().user_name
ep = w.postgres.get_endpoint(name=EP)
host = ep.status.hosts.host
db_res = next(d.name for d in w.postgres.list_databases(parent=BR) if d.status.postgres_database == "databricks_postgres")
print(f"project={PROJECT} branch={BRANCH} host={host} db={db_res} user={me}")

def pg():
    tok = w.postgres.generate_database_credential(endpoint=EP).token
    return psycopg.connect(host=host, dbname="databricks_postgres", user=me, password=tok, sslmode="require", autocommit=True)

# %% [markdown]
# ## 1 · OLTP schema for app write-back

# %%
DDL = """
CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.mitigation_actions (
  action_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  npi_id           TEXT NOT NULL,
  material_id      TEXT,
  action_type      TEXT NOT NULL CHECK (action_type IN ('DUAL_SOURCE_EXPEDITE','CAPACITY_RESERVATION','PULL_AHEAD_BUY',
                                                       'YIELD_SPRINT','LINE_REALLOCATION','PHASED_RAMP_WITH_OEM')),
  title            TEXT NOT NULL,
  rationale        TEXT,
  status           TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED','APPROVED','IN_PROGRESS','DONE','REJECTED')),
  owner            TEXT,
  due_date         DATE,
  estimated_cost_usd NUMERIC(14,2),
  expected_risk_reduction NUMERIC(6,4),
  effect_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
  source           TEXT NOT NULL DEFAULT 'MANUAL' CHECK (source IN ('MANUAL','AI_ADVISOR')),
  created_by       TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_actions_npi ON ops.mitigation_actions (npi_id, status);
CREATE TABLE IF NOT EXISTS ops.gate_signoffs (
  signoff_id       TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  npi_id           TEXT NOT NULL,
  gate             TEXT NOT NULL CHECK (gate IN ('G3','G4','G5')),
  decision         TEXT NOT NULL CHECK (decision IN ('GO','CONDITIONAL_GO','HOLD')),
  conditions       TEXT,
  risk_score_at_signoff NUMERIC(6,4),
  signed_by        TEXT NOT NULL,
  signed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ops.mitigation_actions DROP CONSTRAINT IF EXISTS mitigation_actions_source_check;
ALTER TABLE ops.mitigation_actions ADD CONSTRAINT mitigation_actions_source_check CHECK (source IN ('MANUAL','AI_ADVISOR'));
ALTER TABLE ops.mitigation_actions REPLICA IDENTITY FULL;   -- required by Lakehouse Sync (CDC)
ALTER TABLE ops.gate_signoffs REPLICA IDENTITY FULL;
"""
with pg() as c:
    c.execute(DDL)
    print(c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='ops' ORDER BY 1").fetchall())

# %% [markdown]
# ## 2 · Seed realistic in-flight actions on *other* at-risk launches
# (the hero launch AFT-7200 is left untouched — its mitigation is committed live in the demo)

# %%
# Re-runs must reproduce the same seeds: earlier seeds change the scores they are chosen from, so remove them
# first and wait for the event-driven re-score, then pick from un-mitigated scores.
RESCORE_JOB = next(j.job_id for j in w.jobs.list(name="npi-launch-readiness-rescore-on-action"))
t_clear = int(time.time() * 1000)
with pg() as c:
    cleared = c.execute("DELETE FROM ops.mitigation_actions WHERE rationale LIKE 'Seeded:%' RETURNING action_id").fetchall()
if cleared:
    print(f"cleared {len(cleared)} earlier seeds; waiting for the re-score")
    for _ in range(90):
        runs = [r for r in w.jobs.list_runs(job_id=RESCORE_JOB, limit=5) if r.start_time and r.start_time > t_clear]
        if any(r.state and str(r.state.life_cycle_state).endswith("TERMINATED") for r in runs):
            break
        time.sleep(20)
    else:
        raise TimeoutError("re-score after clearing seeds did not run")

# pick the playbook action that matches each launch's dominant driver (what a planner would actually do)
top = spark.sql(f"""
  SELECT r.npi_id, r.npi_manager, r.worst_material_gap_weeks, r.min_coverage_at_predicted_yield, r.predicted_yield_gap_pts,
         g.material_id AS gap_mat, g.material_desc AS gap_desc, r.binding_component_id, r.binding_component_desc
  FROM {FQ}.gold_launch_risk_scores r
  JOIN (SELECT npi_id, max_by(material_id, material_gap_weeks) material_id, max_by(material_desc, material_gap_weeks) material_desc
        FROM {FQ}.gold_component_readiness GROUP BY npi_id) g USING (npi_id)
  WHERE r.risk_tier = 'HIGH' AND r.npi_id <> 'NPI-2027-014'
  ORDER BY r.revenue_at_risk_usd DESC LIMIT 6""").collect()
status = ["IN_PROGRESS", "APPROVED", "PROPOSED", "APPROVED", "PROPOSED", "PROPOSED"]
seeds = []
for r, st in zip(top, status):
    if r.worst_material_gap_weeks > 2:
        t, mat, desc, title, eff, cost = "PULL_AHEAD_BUY", r.gap_mat, r.gap_desc, "Pre-build 6 weeks of safety stock before SOP", {"buffer_weeks": 6}, 60000
    elif r.min_coverage_at_predicted_yield < 1:
        t, mat, desc, title, eff, cost = "CAPACITY_RESERVATION", r.binding_component_id, r.binding_component_desc, "Reserve +35% weekly capacity with qualified supplier", {"capacity_uplift_pct": 35}, 120000
    else:
        t, mat, desc, title, eff, cost = "YIELD_SPRINT", None, None, "DOE sprint on coat weight & cure profile", {"yield_gain_pts": 6}, 95000
    seeds.append((r.npi_id, mat, t, f"{title}{'' if mat is None else ' - ' + desc}",
                  "Seeded: in-flight action from weekly launch-readiness review", st, r.npi_manager, cost, json.dumps(eff)))
with pg() as c:
    c.execute("DELETE FROM ops.mitigation_actions WHERE rationale LIKE 'Seeded:%'")
    c.cursor().executemany("""INSERT INTO ops.mitigation_actions (npi_id, material_id, action_type, title, rationale, status, owner,
                     due_date, estimated_cost_usd, effect_json, source, created_by)
                     VALUES (%s,%s,%s,%s,%s,%s,%s, CURRENT_DATE + 21, %s, %s::jsonb, 'MANUAL', 'seed')""", seeds)
    for row in c.execute("SELECT npi_id, action_type, status, title FROM ops.mitigation_actions ORDER BY npi_id").fetchall():
        print(row)

# %% [markdown]
# ## 3 · Lakehouse Sync: Postgres `ops` schema → UC Delta CDC history

# %%
from databricks.sdk.errors import NotFound
try:
    w.postgres.create_cdf_config(parent=db_res, cdf_config=CdfConfig(catalog=CATALOG, schema=SCHEMA, postgres_schema="ops"),
                                 cdf_config_id="npi_ops_to_uc").wait()
    print("created CDF config npi_ops_to_uc")
except Exception as e:
    if "already exists" not in str(e).lower():
        raise
    print("CDF config already exists")
# Lakehouse Sync materializes one SCD2 CDC history table per Postgres table in the target UC schema
for _ in range(40):
    names = {t.name for t in w.tables.list(catalog_name=CATALOG, schema_name=SCHEMA)}
    if {"lb_mitigation_actions_history", "lb_gate_signoffs_history"} <= names:
        break
    time.sleep(15)
print(spark.sql(f"SELECT _pg_change_type, count(*) n FROM {FQ}.lb_mitigation_actions_history GROUP BY 1").toPandas().to_string(index=False))

# %% [markdown]
# ## 4 · Synced tables: UC gold → Lakebase `serving` schema (triggered after each scoring run)

# %%
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SYNC_META_SCHEMA} COMMENT 'Pipeline metadata for Lakebase synced tables'")
SYNCS = [("gold_launch_risk_scores", "launch_risk_scores", ["npi_id"], "TRIGGERED"),
         ("gold_component_readiness", "component_readiness", ["npi_id", "material_id"], "TRIGGERED"),
         ("gold_ramp_supply_curve", "ramp_supply_curve", ["npi_id", "week_rel_sop"], "TRIGGERED"),
         ("gold_launch_risk_history", "launch_risk_history", ["npi_id", "scored_at"], "TRIGGERED"),
         ("silver_mitigation_playbook", "mitigation_playbook", ["action_type"], "SNAPSHOT")]
if spark.catalog.tableExists(f"{FQ}.gold_launch_briefs"):
    SYNCS.append(("gold_launch_briefs", "launch_briefs", ["npi_id"], "TRIGGERED"))
spark.sql(f"ALTER TABLE {FQ}.gold_launch_risk_history SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
for src, dst, pk, mode in SYNCS:
    sid = f"{LB_CATALOG}.serving.{dst}"
    try:
        w.postgres.get_synced_table(name=f"synced_tables/{sid}")
        print(f"exists: {sid}")
        continue
    except NotFound:
        pass
    w.postgres.create_synced_table(synced_table_id=sid, synced_table=SyncedTable(spec=SyncedTableSpec(
        source_table_full_name=f"{FQ}.{src}", primary_key_columns=pk, scheduling_policy=Policy(mode), branch=BR,
        postgres_database="databricks_postgres", create_database_objects_if_missing=True,
        new_pipeline_spec=NewPipelineSpec(storage_catalog=CATALOG, storage_schema=SYNC_META_SCHEMA)))).wait()
    print(f"created: {sid}  <- {FQ}.{src} [{mode}]")

# %%
for _ in range(60):
    states = {}
    for _, dst, _, _ in SYNCS:
        t = w.postgres.get_synced_table(name=f"synced_tables/{LB_CATALOG}.serving.{dst}")
        states[dst] = (str(t.status.detailed_state) if t.status else "?", getattr(t.status, "pipeline_id", None))
    if all("ONLINE" in s or "FAILED" in s for s, _ in states.values()):
        break
    time.sleep(20)
for k, (s, pid) in states.items():
    print(f"{k:24s} {s:45s} pipeline={pid}")
json.dump({k: pid for k, (s, pid) in states.items()}, open("../resources/synced_table_pipelines.json", "w"), indent=2)

# %%
with pg() as c:
    for t in ["launch_risk_scores", "component_readiness", "ramp_supply_curve", "launch_risk_history", "mitigation_playbook"]:
        print(t, c.execute(f"SELECT count(*) FROM serving.{t}").fetchone()[0])
    print(c.execute("SELECT npi_id, product_code, risk_tier, round(risk_score::numeric,3), binding_component_desc FROM serving.launch_risk_scores ORDER BY revenue_at_risk_usd DESC LIMIT 5").fetchall())
