# %% [markdown]
# # 01 · Generate & land raw source-system extracts (synthetic)
#
# **Altura Bonding & Tapes · NPI Launch Readiness Control Tower**
#
# Emulates the nightly extracts that land from Altura's systems of record into a Unity Catalog
# **landing volume**, which Lakeflow (Auto Loader) then ingests incrementally:
#
# | Source system | Extract | Format |
# |---|---|---|
# | SAP | `MARA` material master, `LFA1` vendors, `ZQM_SRC_QUAL` supplier qualification / approved sources, `STPO` BOM, `EKPO` open POs | CSV (SAP field names) |
# | MES | coating-line batch runs (pilot + production) | JSON lines |
# | PLM | NPI project register, stage-gate events | JSON lines |
# | OEM EDI | DELFOR-style weekly program demand | CSV |
# | Mfg Eng | coating line capacity | CSV |
# | Commercial | historical launch post-mortems | CSV |
#
# * `batch=1` → full extract as of **2026-11-16**
# * `batch=2` → **this morning's (2026-11-23) incremental drop**: two MES production-trial runs for
#   the AFT-7200 launch and a supplier capacity-allocation notice from Arden Specialty Polymers.
#
# All names (products, suppliers, OEMs, plants) are fictional. No real customer data is used.

# %%
import io, os, sys
sys.path.insert(0, os.path.abspath("../src"))
from npi.env import CATALOG, SCHEMA, LANDING, get_spark, get_ws, widget
from npi.datagen import generate, BATCH1_DATE, BATCH2_DATE

BATCH = widget("batch", "all")      # "1", "2" or "all"
RESET = widget("reset", "true") == "true"
spark, w = get_spark(), get_ws()
print(f"Target: {CATALOG}.{SCHEMA}  landing volume: {LANDING}  batch={BATCH} reset={RESET}")

# %%
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} COMMENT "
          "'Altura BTD NPI Launch Readiness Control Tower - synthetic data (FE Bar build)'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.landing COMMENT "
          "'Raw landing zone for SAP / MES / PLM / OEM EDI extracts (Auto Loader source)'")
def _rm(path):
    for e in w.files.list_directory_contents(path):
        _rm(e.path) if e.is_directory else w.files.delete(e.path)
    w.files.delete_directory(path)

if RESET and BATCH in ("1", "all"):
    # wipe landing zone so the demo is reproducible from scratch
    for d in w.files.list_directory_contents(LANDING):
        if d.is_directory:
            _rm(d.path)
    print("Landing zone reset.")

# %%
raw = generate()
JSONL = {"mes/batch_runs", "plm/npi_projects", "plm/stage_gates"}

def land(tables: dict, as_of):
    tag = as_of.strftime("%Y%m%d")
    out = []
    for key, df in tables.items():
        name = key.split("/")[-1]
        if key in JSONL:
            body, ext = df.to_json(orient="records", lines=True, date_format="iso"), "jsonl"
        else:
            body, ext = df.to_csv(index=False), "csv"
        path = f"{LANDING}/{key}/{name}_{tag}.{ext}"
        w.files.upload(path, io.BytesIO(body.encode()), overwrite=True)
        out.append((key, len(df), path))
    return out

landed = []
if BATCH in ("1", "all"):
    landed += land(raw.batch1, BATCH1_DATE)
if BATCH in ("2", "all"):
    landed += land(raw.batch2, BATCH2_DATE)
for k, n, p in landed:
    print(f"{k:28s} {n:>8,} rows -> {p}")

# %% [markdown]
# ### Sanity check: the story is in the raw data
# Historical launch outcomes (what the commercial team's post-mortems recorded) and the hero launch.

# %%
o = raw.batch1["commercial/launch_outcomes"]
failed = (o.slip_weeks > 2) | (o.otif_first_90d < 0.85)
print(f"Historical launches 2020-2026: {len(o)}")
print(f"  launches that missed ramp (slip>2w or 90-day OTIF<85%): {failed.mean():.1%}")
print(f"  OEM platforms lost: {o.platform_lost.sum()}  (lifetime value ${o.lost_platform_value_usd.sum()/1e6:,.0f}M)")
print(f"  expedite cost ${o.expedite_cost_usd.sum()/1e6:,.1f}M | E&O ${o.eo_writeoff_usd.sum()/1e6:,.1f}M | "
      f"deferred revenue ${o.deferred_revenue_usd.sum()/1e6:,.1f}M")
print(o[failed].root_cause_primary.value_counts().to_string())

# %%
p = raw.batch1["plm/npi_projects"]
print(p[p.npi_id == "NPI-2027-014"].T.to_string())
