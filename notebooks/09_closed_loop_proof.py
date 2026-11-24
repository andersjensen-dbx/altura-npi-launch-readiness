# %% [markdown]
# # 09 · Closed-loop proof: a decision in the app changes the risk the business sees
#
# This notebook exercises the **integrated** journey end to end, exactly as the Control Tower app does,
# and records every hop as text evidence:
#
# 1. Read AFT-7200's current risk from **Lakebase** (`serving.launch_risk_scores` - synced from UC gold).
# 2. Commit a mitigation package into **Lakebase OLTP** (`ops.mitigation_actions`), as the app's
#    "Approve & commit" button does.
# 3. **Lakehouse Sync** streams the inserts to Unity Catalog (`lb_mitigation_actions_history`, CDC).
# 4. The **table-update trigger** fires the Lakeflow Job `npi-launch-readiness-rescore-on-action`
#    (ML re-score with UC champion models -> gold tables -> Lakebase synced tables).
# 5. Read the new risk back from Lakebase.
# 6. Clean up (delete the actions, re-score) so the live demo starts from the un-mitigated baseline.

# %%
import os, sys, json, time
sys.path.insert(0, os.path.abspath("../src"))
import psycopg
from npi.env import FQ, get_spark, get_ws

w, spark = get_ws(), get_spark()
EP = "projects/npi-readiness/branches/production/endpoints/primary"
HERO = "NPI-2027-014"
JOB = next(j.job_id for j in w.jobs.list(name="npi-launch-readiness-rescore-on-action"))
me = w.current_user.me().user_name

def pg():
    return psycopg.connect(host=w.postgres.get_endpoint(name=EP).status.hosts.host, dbname="databricks_postgres", user=me,
                           password=w.postgres.generate_database_credential(endpoint=EP).token, sslmode="require", autocommit=True)

def lakebase_risk():
    with pg() as c:
        return c.execute("SELECT risk_score, baseline_risk_score, revenue_at_risk_usd, actions_applied, scored_at "
                         "FROM serving.launch_risk_scores WHERE npi_id = %s", (HERO,)).fetchone()

def wait_for_rescore(after_ms, label):
    """Wait for a rescore-job run that STARTED after `after_ms` to finish (triggered by the table-update trigger)."""
    for _ in range(90):
        runs = [r for r in w.jobs.list_runs(job_id=JOB, limit=5) if r.start_time and r.start_time > after_ms]
        done = [r for r in runs if r.state and str(r.state.life_cycle_state).endswith(("TERMINATED", "INTERNAL_ERROR", "SKIPPED"))]
        if done:
            r = done[-1]
            print(f"[{label}] rescore run {r.run_id} trigger={r.trigger} result={r.state.result_state} "
                  f"duration={(r.end_time - r.start_time)/1000:.0f}s")
            return r
        time.sleep(20)
    raise TimeoutError("re-score job did not run")

# Idempotent re-runs: remove proof actions left by an interrupted earlier run, and wait for the re-score.
t_clean = int(time.time() * 1000)
with pg() as c:
    stale = [r[0] for r in c.execute("DELETE FROM ops.mitigation_actions WHERE rationale = 'Closed-loop proof (notebook 09)' "
                                     "RETURNING action_id").fetchall()]
if stale:
    print(f"removed {len(stale)} proof actions from an earlier run; waiting for the re-score")
    wait_for_rescore(t_clean, "pre-clean")

r0 = lakebase_risk()
print(f"BEFORE risk={float(r0[0]):.1%} baseline={float(r0[1]):.1%} revenue_at_risk=${float(r0[2])/1e6:.1f}M actions_applied={r0[3]} scored_at={r0[4]}")

# %% [markdown]
# ## 2 · Commit the package in Lakebase (what "Approve & commit" in the app writes)

# %%
mats = {r.material_desc.split()[0]: r.material_id for r in
        spark.sql(f"SELECT material_id, material_desc FROM {FQ}.gold_component_readiness WHERE npi_id = '{HERO}'").collect()}
play = {r.action_type: (r.effect_json, r.typical_cost_usd) for r in spark.table(f"{FQ}.silver_mitigation_playbook").collect()}
package = [("DUAL_SOURCE_EXPEDITE", mats["FC-220"], "Fast-track Kvarn PPAP for FC-220 foam core"),
           ("PULL_AHEAD_BUY", mats["FC-220"], "Pre-build FC-220 safety stock before build-ahead"),
           ("PULL_AHEAD_BUY", mats["RL-310"], "Pre-build RL-310 liner stock"),
           ("YIELD_SPRINT", None, "DOE yield sprint on US20-F02 (coat weight / cure)")]
t_commit = int(time.time() * 1000)
with pg() as c:
    ids = [c.execute("""INSERT INTO ops.mitigation_actions (npi_id, material_id, action_type, title, rationale, status, owner,
                                 estimated_cost_usd, effect_json, source, created_by)
                        VALUES (%s,%s,%s,%s,'Closed-loop proof (notebook 09)','APPROVED','Hannah Lindgren',%s,%s::jsonb,'AI_ADVISOR',%s)
                        RETURNING action_id""", (HERO, m, t, title, play[t][1], play[t][0], me)).fetchone()[0]
           for t, m, title in package]
print(f"committed {len(ids)} APPROVED actions to Lakebase ops.mitigation_actions")

# %% [markdown]
# ## 3-4 · Lakehouse Sync -> Unity Catalog -> table-update trigger -> re-score job

# %%
for _ in range(30):
    n = spark.sql(f"SELECT count(*) FROM {FQ}.lb_mitigation_actions_history WHERE action_id IN ({','.join(repr(i) for i in ids)})").first()[0]
    if n >= len(ids):
        break
    time.sleep(10)
print(f"Lakehouse Sync: {n}/{len(ids)} action inserts visible in UC {FQ}.lb_mitigation_actions_history "
      f"after {(time.time()*1000 - t_commit)/1000:.0f}s")
run = wait_for_rescore(t_commit, "commit")

# %% [markdown]
# ## 5 · New risk, served from Lakebase to the app

# %%
r1 = lakebase_risk()
print(f"AFTER   risk={float(r1[0]):.1%} baseline={float(r1[1]):.1%} revenue_at_risk=${float(r1[2])/1e6:.1f}M actions_applied={r1[3]} scored_at={r1[4]}")
print(f"=> committed package moved AFT-7200 from {float(r0[0]):.0%} to {float(r1[0]):.0%} ramp-failure risk; "
      f"${(float(r0[2]) - float(r1[2]))/1e6:.1f}M of year-1 revenue protected; end-to-end latency "
      f"{(time.time()*1000 - t_commit)/60000:.1f} min")
with pg() as c:
    for row in c.execute("""SELECT week_rel_sop, oem_demand_m2, supportable_output_m2, shortfall_m2 FROM serving.ramp_supply_curve
                            WHERE npi_id = %s AND week_rel_sop BETWEEN 0 AND 12 ORDER BY week_rel_sop""", (HERO,)).fetchall():
        print("  week +%-2s demand %6.0f  supportable %6.0f  shortfall %6.0f m2" % row)

# %% [markdown]
# ## 6 · Restore the demo baseline

# %%
t_reset = int(time.time() * 1000)
with pg() as c:
    c.execute("DELETE FROM ops.mitigation_actions WHERE action_id = ANY(%s)", (ids,))
print("deleted proof actions; waiting for CDC + re-score")
wait_for_rescore(t_reset, "reset")
r2 = lakebase_risk()
print(f"RESTORED risk={float(r2[0]):.1%} actions_applied={r2[3]}")
