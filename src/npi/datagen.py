"""
Synthetic source-system data for the Altura Industries' Bonding & Tapes Division (BTD)
NPI Launch Readiness Control Tower.

All data is SYNTHETIC. Product names, suppliers, OEMs and plants are fictional.

The generator emulates the raw extracts that would land from real Altura source systems:
  SAP ECC/S4  : material master (MARA), vendor master (LFA1), supplier qualification /
                approved source list (custom ZQM_SRC_QUAL), BOM (STPO), open POs (EKPO)
  MES         : coating-line batch runs (pilot + production), JSON lines
  PLM         : NPI project register + stage-gate events (G0..G5), JSON
  OEM / EDI   : customer program demand schedules (DELFOR-style weekly forecast), CSV
  Mfg Eng     : coating line capacity & utilization, CSV
  Commercial  : historical launch post-mortems (outcomes), CSV

Story (see README): products pass pilot, but ramp plans are built on pilot-scale
assumptions (pilot-qualified / single-source materials, pilot-line yields). The
historical launches carry the causal signal (supply readiness + yield gap ->
slip / low OTIF / lost OEM platforms) that the ML model learns; the active
pipeline contains an engineered hero launch (AFT-7200 for Northstar Motors EV-X9).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

TODAY = date(2026, 11, 23)          # "as-of" date for the demo
BATCH1_DATE = date(2026, 11, 16)    # initial full extract
BATCH2_DATE = date(2026, 11, 23)    # this morning's incremental drop
SEED = 7

# ----------------------------------------------------------------------------------
# Static reference data
# ----------------------------------------------------------------------------------
PLANTS = [
    # code, name, location, region
    ("US10", "Midwest Tape Operations", "Minnesota, US", "NA"),
    ("US20", "Southern Coating Center", "Alabama, US", "NA"),
    ("US30", "Heartland Converting", "Missouri, US", "NA"),
    ("MX10", "Bajio Converting", "Guanajuato, MX", "NA"),
    ("DE10", "Rhine Adhesives Plant", "NRW, DE", "EMEA"),
    ("CN10", "East China Tape Plant", "Jiangsu, CN", "APAC"),
]

# line_id, plant, technology, capacity m2/week, commissioned year, base utilization
LINES = [
    ("US10-PL01", "US10", "PILOT_UV", 9_000, 2018, 0.55),
    ("US10-PL02", "US10", "PILOT_SOLVENT", 8_000, 2015, 0.60),
    ("US10-C01", "US10", "SOLVENT_COAT", 210_000, 2004, 0.78),
    ("US10-C02", "US10", "UV_CURE", 160_000, 2016, 0.74),
    ("US20-C03", "US20", "HOTMELT_COAT", 240_000, 2009, 0.81),
    ("US20-F02", "US20", "FOAM_EXTRUSION", 120_000, 2011, 0.86),
    ("US20-C04", "US20", "UV_CURE", 150_000, 2021, 0.69),
    ("US30-C05", "US30", "SOLVENT_COAT", 190_000, 1998, 0.83),
    ("MX10-C06", "MX10", "HOTMELT_COAT", 170_000, 2019, 0.72),
    ("DE10-C07", "DE10", "SOLVENT_COAT", 140_000, 2007, 0.80),
    ("DE10-F03", "DE10", "FOAM_EXTRUSION", 90_000, 2017, 0.77),
    ("CN10-C08", "CN10", "UV_CURE", 200_000, 2020, 0.75),
    ("CN10-C09", "CN10", "HOTMELT_COAT", 180_000, 2013, 0.84),
]
PILOT_LINES = ["US10-PL01", "US10-PL02"]
PROD_LINES = [l for l in LINES if l[2] not in ("PILOT_UV", "PILOT_SOLVENT")]

# family code -> (name, production technology, pilot line, complexity range, segments+weights,
#                  price $/m2 range, component categories)
FAMILIES = {
    "SAF": ("Structural Acrylic Foam Tape", "FOAM_EXTRUSION", "US10-PL01", (3, 5),
            {"EV_OEM": .45, "AUTO_TIER1": .35, "INDUSTRIAL": .20}, (6.0, 11.0),
            ["ACRYLIC_MONOMER", "FOAM_CORE", "RELEASE_LINER", "PRIMER", "CROSSLINKER", "PACKAGING_CORE"]),
    "TIT": ("Battery Thermal Interface Tape", "UV_CURE", "US10-PL01", (3, 5),
            {"EV_OEM": .75, "AUTO_TIER1": .25}, (9.0, 16.0),
            ["ACRYLIC_MONOMER", "THERMAL_FILLER", "CARRIER_FILM", "RELEASE_LINER", "PHOTOINITIATOR", "PACKAGING_CORE"]),
    "FBT": ("Flame-Barrier Battery Insulation Tape", "SOLVENT_COAT", "US10-PL02", (2, 4),
            {"EV_OEM": .65, "AUTO_TIER1": .35}, (7.0, 12.0),
            ["ACRYLIC_MONOMER", "FLAME_RETARDANT", "CARRIER_FILM", "RELEASE_LINER", "CROSSLINKER", "PACKAGING_CORE"]),
    "OCA": ("Optically Clear Display Adhesive", "UV_CURE", "US10-PL01", (2, 4),
            {"ELECTRONICS": 1.0}, (14.0, 24.0),
            ["ACRYLIC_MONOMER", "CARRIER_FILM", "RELEASE_LINER", "PHOTOINITIATOR", "PACKAGING_CORE"]),
    "LVT": ("Low-VOC Interior Trim Tape", "HOTMELT_COAT", "US10-PL02", (1, 3),
            {"AUTO_TIER1": .60, "EV_OEM": .25, "INDUSTRIAL": .15}, (2.5, 5.0),
            ["TACKIFIER_RESIN", "CARRIER_FILM", "RELEASE_LINER", "PACKAGING_CORE"]),
    "ADT": ("Acoustic Damping Tape", "HOTMELT_COAT", "US10-PL02", (1, 3),
            {"AUTO_TIER1": .50, "EV_OEM": .30, "INDUSTRIAL": .20}, (3.0, 6.0),
            ["TACKIFIER_RESIN", "FOAM_CORE", "RELEASE_LINER", "PACKAGING_CORE"]),
    "DGT": ("Die-Cut Gasket Transfer Tape", "SOLVENT_COAT", "US10-PL02", (1, 3),
            {"ELECTRONICS": .55, "INDUSTRIAL": .45}, (4.0, 8.0),
            ["ACRYLIC_MONOMER", "TACKIFIER_RESIN", "RELEASE_LINER", "CROSSLINKER", "PACKAGING_CORE"]),
}
FAMILY_MIX = {"SAF": .20, "TIT": .16, "FBT": .12, "OCA": .14, "LVT": .14, "ADT": .10, "DGT": .14}

# category -> (prefix, UoM, lead-time weeks range, unit cost range, qty per 1000 m2 range)
CATEGORIES = {
    "ACRYLIC_MONOMER": ("ACM", "KG", (3, 7), (2.2, 4.8), (38, 70)),
    "TACKIFIER_RESIN": ("TKR", "KG", (5, 10), (3.0, 6.5), (20, 45)),
    "FOAM_CORE":       ("FCR", "M2", (8, 15), (1.1, 3.4), (1010, 1060)),
    "RELEASE_LINER":   ("RLN", "M2", (5, 12), (0.18, 0.65), (1015, 1050)),
    "CARRIER_FILM":    ("CFM", "M2", (5, 11), (0.25, 1.20), (1010, 1040)),
    "THERMAL_FILLER":  ("THF", "KG", (11, 20), (9.0, 28.0), (45, 95)),
    "FLAME_RETARDANT": ("FRT", "KG", (7, 14), (5.0, 14.0), (18, 40)),
    "PRIMER":          ("PRM", "KG", (3, 7), (6.0, 15.0), (2, 6)),
    "CROSSLINKER":     ("XLK", "KG", (3, 8), (8.0, 22.0), (0.8, 2.5)),
    "PHOTOINITIATOR":  ("PHI", "KG", (5, 11), (25.0, 60.0), (0.5, 1.8)),
    "PACKAGING_CORE":  ("PKG", "EA", (2, 4), (0.4, 1.5), (10, 14)),
}

SUPPLIER_PREFIX = ["Arden", "Kvarn", "Halden", "Brixton", "Corvane", "Tamsin", "Ostrava", "Velde", "Marrow",
                   "Quintero", "Selby", "Hargrove", "Nakamura", "Ilsen", "Dunmore", "Ferrant", "Lysander",
                   "Petrov", "Wexley", "Zhenghe", "Bellamy", "Castellan", "Rennick", "Sorensen", "Talbot",
                   "Ueda", "Varga", "Whitlock", "Yoshida", "Almquist", "Bragg", "Cordova", "Delacroix",
                   "Eastgate", "Fairholt", "Granger", "Hollis", "Ingram", "Juniper", "Kessler", "Lindqvist",
                   "Moravec", "Northam", "Okafor", "Pemberton", "Rasmussen", "Stroud", "Thorne", "Underhill",
                   "Vasquez", "Winslow", "Xu", "Yardley", "Zeller", "Ashdown"]
SUPPLIER_SUFFIX = ["Specialty Polymers", "Materials AB", "Chemical Co.", "Films Ltd.", "Advanced Materials",
                   "Coatings GmbH", "Industries", "Performance Chemicals", "Polymer Works", "Converting Inc."]
SUPPLIER_COUNTRIES = {"US": .40, "DE": .14, "CN": .16, "JP": .08, "KR": .06, "MX": .06, "SE": .04, "BE": .06}

OEMS = {
    "EV_OEM": [("Northstar Motors", "NSM"), ("Voltaris EV", "VLT"), ("Kestrel Automotive", "KST"),
               ("Halvorsen Truck", "HVT")],
    "AUTO_TIER1": [("Tessaro Systems", "TSS"), ("Brightline Interiors", "BLI"), ("Ostrander Modules", "OSM")],
    "ELECTRONICS": [("Aurion Electronics", "AUR"), ("Meridian Devices", "MRD"), ("Lumora Displays", "LMR")],
    "INDUSTRIAL": [("Corridor Building Products", "CBP"), ("Ironvale Equipment", "IVE")],
}

MITIGATION_PLAYBOOK = [
    # action_type, description, effect keys (applied by scoring), typical cost $
    ("DUAL_SOURCE_EXPEDITE", "Fast-track PPAP of an alternate supplier for the constrained component",
     {"qual_pull_in_weeks": 6}, 85_000),
    ("CAPACITY_RESERVATION", "Contract incremental weekly capacity with the qualified supplier",
     {"capacity_uplift_pct": 35}, 120_000),
    ("PULL_AHEAD_BUY", "Pre-build safety stock of the long-lead component before SOP",
     {"buffer_weeks": 6}, 60_000),
    ("YIELD_SPRINT", "Process-engineering sprint on the production line (DOE on coat weight / cure)",
     {"yield_gain_pts": 6}, 95_000),
    ("LINE_REALLOCATION", "Move launch volume to a less-utilized line with matching technology",
     {"utilization_delta": -0.12}, 40_000),
    ("PHASED_RAMP_WITH_OEM", "Negotiate a phased volume ramp with the OEM program team",
     {"ramp_peak_factor": 0.80}, 15_000),
]

GATES = [("G0", "Idea Screen"), ("G1", "Feasibility"), ("G2", "Development"),
         ("G3", "Pilot Validated / Scale-Up Decision"), ("G4", "Launch Readiness"),
         ("G5", "Commercial Launch (SOP)")]


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass
class RawData:
    batch1: dict[str, pd.DataFrame]
    batch2: dict[str, pd.DataFrame]
    truth: pd.DataFrame  # generator-side ground truth (not landed; used for validation only)


# ----------------------------------------------------------------------------------
# Generator
# ----------------------------------------------------------------------------------
def generate(n_hist: int = 420, n_active: int = 36, seed: int = SEED) -> RawData:
    rng = np.random.default_rng(seed)

    # ---------------- plants & lines ----------------
    plants = pd.DataFrame(PLANTS, columns=["WERKS", "PLANT_NAME", "LOCATION", "REGION"])
    lines = pd.DataFrame(LINES, columns=["LINE_ID", "WERKS", "TECHNOLOGY", "CAPACITY_M2_WK",
                                         "COMMISSIONED_YEAR", "BASE_UTILIZATION"])
    line_tech = dict(zip(lines.LINE_ID, lines.TECHNOLOGY))
    line_age = dict(zip(lines.LINE_ID, 2026 - lines.COMMISSIONED_YEAR))
    line_util = dict(zip(lines.LINE_ID, lines.BASE_UTILIZATION))
    line_cap = dict(zip(lines.LINE_ID, lines.CAPACITY_M2_WK))
    line_plant = dict(zip(lines.LINE_ID, lines.WERKS))

    # ---------------- suppliers ----------------
    n_sup = len(SUPPLIER_PREFIX)
    countries = rng.choice(list(SUPPLIER_COUNTRIES), n_sup, p=list(SUPPLIER_COUNTRIES.values()))
    risk = rng.choice([1, 2, 3, 4, 5], n_sup, p=[.22, .34, .26, .12, .06])
    suppliers = pd.DataFrame({
        "LIFNR": [f"V{100200 + i * 7}" for i in range(n_sup)],
        "NAME1": [f"{p} {SUPPLIER_SUFFIX[i % len(SUPPLIER_SUFFIX)]}" for i, p in enumerate(SUPPLIER_PREFIX)],
        "LAND1": countries,
        "ZZ_RISK_TIER": risk,
        "ZZ_OTD_PCT": np.clip(rng.normal(96 - 2.2 * risk, 2.0), 78, 99.5).round(1),
    })
    # hero suppliers fixed
    suppliers.loc[0, ["NAME1", "LAND1", "ZZ_RISK_TIER", "ZZ_OTD_PCT"]] = ["Arden Specialty Polymers", "US", 3, 91.4]
    suppliers.loc[1, ["NAME1", "LAND1", "ZZ_RISK_TIER", "ZZ_OTD_PCT"]] = ["Kvarn Materials AB", "SE", 2, 95.8]
    sup_ids = suppliers.LIFNR.tolist()

    # ---------------- established materials (shared, mostly multi-sourced) ----------------
    mat_rows, src_rows = [], []
    est_by_cat: dict[str, list[str]] = {}
    mat_seq = 1000

    def new_material(cat: str, novel: bool, name: str | None = None, base_demand_factor=1.0):
        nonlocal mat_seq
        prefix, uom, lt, cost, _ = CATEGORIES[cat]
        mat_seq += int(rng.integers(3, 17))
        matnr = f"RM-{prefix}-{mat_seq}"
        lead_w = int(rng.integers(lt[0], lt[1] + 1)) + (3 if novel else 0)
        grade = f"{'NX' if novel else 'G'}{mat_seq % 1000:03d}"
        mat_rows.append({
            "MATNR": matnr,
            "MAKTX": name or f"{cat.replace('_', ' ').title()} {grade}",
            "MTART": "ROH",
            "MATKL": cat,
            "MEINS": uom,
            "PLIFZ": lead_w * 7,
            "ZZ_NOVEL_FLAG": "X" if novel else "",
            # existing base-business draw on the same supply (competes with NPI ramp)
            "ZZ_BASE_WKLY_DEMAND": round(float(rng.lognormal(*{"KG": (9.0, 0.6), "M2": (12.2, 0.5),
                                                                "EA": (6.5, 0.4)}[uom]) * base_demand_factor)
                                         if not novel else 0.0, 1),
            "STPRS": round(float(rng.uniform(*cost)), 3),
        })
        return matnr, lead_w

    for cat in CATEGORIES:
        est_by_cat[cat] = []
        for _ in range({"ACRYLIC_MONOMER": 10, "TACKIFIER_RESIN": 7, "FOAM_CORE": 6, "RELEASE_LINER": 8,
                        "CARRIER_FILM": 7, "THERMAL_FILLER": 5, "FLAME_RETARDANT": 5, "PRIMER": 4,
                        "CROSSLINKER": 5, "PHOTOINITIATOR": 4, "PACKAGING_CORE": 3}[cat]):
            matnr, lead_w = new_material(cat, novel=False)
            est_by_cat[cat].append(matnr)
            n_src = rng.choice([1, 2, 3], p=[.22, .48, .30])
            base = mat_rows[-1]["ZZ_BASE_WKLY_DEMAND"]
            for s in rng.choice(sup_ids[2:], n_src, replace=False):
                approved = date(2010, 1, 1) + timedelta(days=int(rng.integers(0, 3400)))
                headroom = 3.0 if cat == "PACKAGING_CORE" else float(rng.uniform(1.12, 1.9))
                src_rows.append({
                    "MATNR": matnr, "LIFNR": s, "QUAL_STATUS": "QUALIFIED",
                    "PPAP_START": (approved - timedelta(days=int(rng.integers(60, 200)))).isoformat(),
                    "PPAP_APPROVED": approved.isoformat(), "PPAP_PLANNED": approved.isoformat(),
                    "CAP_WKLY": round(base * headroom / n_src, 1),
                    "LEAD_DAYS": lead_w * 7 + int(rng.integers(-7, 15)),
                    "NETPR": round(mat_rows[-1]["STPRS"] * float(rng.uniform(0.92, 1.10)), 3), "WAERS": "USD",
                })

    # ---------------- NPI launches ----------------
    fam_codes = list(FAMILY_MIX)
    n_total = n_hist + n_active
    fams = rng.choice(fam_codes, n_total, p=list(FAMILY_MIX.values()))
    # historical SOPs 2020-01 .. 2026-09 ; active SOPs 2027-01 .. 2027-09
    hist_sop = [date(2020, 1, 6) + timedelta(weeks=int(w)) for w in rng.integers(0, 351, n_hist)]
    act_sop = [date(2027, 1, 11) + timedelta(weeks=int(w)) for w in rng.integers(0, 37, n_active)]
    sops = hist_sop + act_sop

    launches, bom_rows, gate_rows, mes_rows, demand_rows, outcome_rows, truth_rows, po_rows = ([] for _ in range(8))
    prod_seq = 3100

    for i in range(n_total):
        is_active = i >= n_hist
        fam = fams[i]
        fname, tech, pilot_line, cx_rng, seg_w, price_rng, comp_cats = FAMILIES[fam]
        seg = rng.choice(list(seg_w), p=list(seg_w.values()))
        oem, oem_code = OEMS[seg][int(rng.integers(0, len(OEMS[seg])))]
        sop = _monday(sops[i])
        prod_seq += int(rng.integers(5, 40))
        product = f"{fam}-{prod_seq}"
        npi_id = f"NPI-{sop.year}-{i % 1000:03d}"
        complexity = int(rng.integers(cx_rng[0], cx_rng[1] + 1))
        novel_chem = bool(rng.random() < (0.45 if fam in ("TIT", "FBT", "SAF") else 0.2))
        # production line: matching tech most of the time; sometimes forced onto mismatched line
        match_lines = [l[0] for l in PROD_LINES if l[2] == tech]
        if rng.random() < 0.8:
            line = match_lines[int(rng.integers(0, len(match_lines)))]
        else:
            line = PROD_LINES[int(rng.integers(0, len(PROD_LINES)))][0]
        pilot_tech = line_tech[pilot_line]
        tech_mismatch = int(not ((pilot_tech == "PILOT_UV" and line_tech[line] == "UV_CURE")
                                 or (pilot_tech == "PILOT_SOLVENT" and line_tech[line] in ("SOLVENT_COAT", "HOTMELT_COAT"))))
        n_pilot = int(np.clip(rng.poisson(6 if not novel_chem else 5), 2, 15))
        pilot_yield = float(np.clip(rng.normal(91 - 0.9 * complexity, 2.2), 80, 97.5))
        price = float(rng.uniform(*price_rng))
        annual_m2 = float(rng.lognormal(13.0 if seg in ("EV_OEM", "AUTO_TIER1") else 12.5, 0.55))
        util_at_sop = float(np.clip(line_util[line] + rng.normal(0.03, 0.06), 0.45, 0.99))
        g3 = sop - timedelta(weeks=int(rng.integers(22, 41)))

        # ---- hero launch overrides (active pipeline) ----
        hero = is_active and i == n_hist + 13
        if hero:
            fam, fname, tech, seg = "SAF", FAMILIES["SAF"][0], "FOAM_EXTRUSION", "EV_OEM"
            comp_cats = FAMILIES["SAF"][6]
            oem, oem_code = "Northstar Motors", "NSM"
            sop = date(2027, 3, 15)
            product, npi_id = "AFT-7200", "NPI-2027-014"
            complexity, novel_chem, line, pilot_line = 5, True, "US20-F02", "US10-PL01"
            tech_mismatch, n_pilot, pilot_yield = 1, 4, 91.6
            price, annual_m2, util_at_sop = 9.85, 1_870_000.0, 0.91
            g3 = date(2026, 10, 5)

        program = f"{oem_code}-{rng.choice(['EVX', 'PLT', 'MOD', 'GEN', 'BX'])}{int(rng.integers(2, 12))}"
        if hero:
            program = "NSM-EVX9"
        year1_rev = annual_m2 * price
        lifetime_value = year1_rev * float(rng.uniform(4.5, 6.5)) if seg in ("EV_OEM", "AUTO_TIER1") \
            else year1_rev * float(rng.uniform(2.0, 3.5))
        product_name = f"{product} {fname}"
        if hero:
            product_name = "AFT-7200 Structural Battery-Enclosure Foam Tape"
            lifetime_value = 96_400_000.0

        as_of = TODAY if is_active else g3
        weeks_to_sop = (sop - as_of).days / 7

        # ---- gates ----
        gate_offsets = {"G0": 100, "G1": 78, "G2": 56}
        gdates = {g: sop - timedelta(weeks=gate_offsets[g] + int(rng.integers(-8, 9))) for g in gate_offsets}
        gdates["G3"] = g3
        gdates["G4"] = sop - timedelta(weeks=int(rng.integers(6, 11)))
        gdates["G5"] = sop
        current_gate = "G5"
        if is_active:
            current_gate = "G4" if gdates["G4"] <= TODAY else "G3"
            if g3 > TODAY:   # make sure every active launch has passed pilot (G3)
                gdates["G3"] = TODAY - timedelta(weeks=int(rng.integers(1, 8)))
        for g, gname in GATES:
            gd = gdates[g]
            if is_active and gd > TODAY:
                continue
            gate_rows.append({"npi_id": npi_id, "gate": g, "gate_name": gname, "gate_date": gd.isoformat(),
                              "decision": "GO", "approver_role": {"G0": "BU Marketing", "G1": "Tech Director",
                              "G2": "Tech Director", "G3": "NPI Steering Committee", "G4": "Supply Chain VP",
                              "G5": "Business Unit President"}[g],
                              "notes": "Pilot criteria met: adhesion, shear, aging within spec" if g == "G3" else ""})

        # ---- BOM: established + novel components ----
        bom = []
        for cat in comp_cats:
            novel_here = novel_chem and cat in ("FOAM_CORE", "THERMAL_FILLER", "FLAME_RETARDANT", "RELEASE_LINER",
                                                 "ACRYLIC_MONOMER", "TACKIFIER_RESIN") and rng.random() < 0.55
            if hero and cat in ("FOAM_CORE", "RELEASE_LINER"):
                novel_here = True
            if hero and cat not in ("FOAM_CORE", "RELEASE_LINER"):
                novel_here = False
            if novel_here:
                nm = None
                if hero and cat == "FOAM_CORE":
                    nm = "FC-220 High-Density Acrylic Foam Core"
                if hero and cat == "RELEASE_LINER":
                    nm = "RL-310 Fluorosilicone PET Release Liner"
                matnr, lead_w = new_material(cat, novel=True, name=nm)
                if hero and cat == "FOAM_CORE":
                    lead_w = 14
                    mat_rows[-1]["PLIFZ"] = 98
                if hero and cat == "RELEASE_LINER":
                    lead_w = 9
                    mat_rows[-1]["PLIFZ"] = 63
                bom.append((matnr, cat, True, lead_w))
            else:
                pool = est_by_cat[cat]
                matnr = pool[int(rng.integers(0, len(pool)))]
                lead_w = next(m["PLIFZ"] for m in mat_rows if m["MATNR"] == matnr) // 7
                bom.append((matnr, cat, False, lead_w))

        # demand schedule (DELFOR-like): weekly m2 from SOP-8 to SOP+26, S-curve to steady state
        steady = annual_m2 / 52
        weeks = np.arange(-8, 27)
        ramp = steady * (0.15 + 0.85 / (1 + np.exp(-(weeks - 4) / 2.2)))
        ramp[weeks < 0] = steady * 0.35   # build-ahead / PPAP & launch stock
        if hero:
            ramp = steady * np.where(weeks < 0, 0.40, 0.30 + 0.75 / (1 + np.exp(-(weeks - 3) / 1.8)))
        peak_m2 = float(ramp.max())
        for w, q in zip(weeks, ramp):
            demand_rows.append({"customer": oem, "program": program, "npi_id": npi_id, "product": product,
                                "week_start": (sop + timedelta(weeks=int(w))).isoformat(),
                                "week_rel_sop": int(w), "forecast_m2": round(float(q * rng.uniform(0.97, 1.03)), 0),
                                "forecast_version": "2026W46"})

        # ---- yield truth ----
        yield_gap = (2.0 + 1.9 * complexity + 4.0 * novel_chem + 5.5 * tech_mismatch + 0.18 * line_age[line]
                     - 0.55 * min(n_pilot, 10) + rng.normal(0, 2.2))
        yield_gap = float(np.clip(yield_gap, 0.5, 28))
        if hero:
            yield_gap = 17.8
        prod_yield = pilot_yield - yield_gap

        # pilot MES runs
        for r in range(n_pilot):
            d = g3 - timedelta(days=int(rng.integers(14, 180)))
            y = float(np.clip(rng.normal(pilot_yield, 1.6), 70, 99.5))
            mes_rows.append({"run_id": f"R{len(mes_rows) + 500000}", "line_id": pilot_line,
                             "plant": line_plant[pilot_line], "product": product, "npi_id": npi_id,
                             "run_type": "PILOT", "run_date": d.isoformat(),
                             "input_m2": round(float(rng.uniform(1800, 4200)), 0),
                             "yield_pct": round(y, 2), "scrap_reason": _scrap(rng, y)})
        # production MES runs for historical launches: 2 runs/day for 12 weeks, ramping toward steady yield
        if not is_active:
            for day in range(84):
                for _ in range(2):
                    ramp_def = (yield_gap * 0.35) * np.exp(-day / 30)
                    y = float(np.clip(rng.normal(prod_yield - ramp_def, 2.4), 40, 99))
                    mes_rows.append({"run_id": f"R{len(mes_rows) + 500000}", "line_id": line,
                                     "plant": line_plant[line], "product": product, "npi_id": npi_id,
                                     "run_type": "PRODUCTION", "run_date": (sop + timedelta(days=day)).isoformat(),
                                     "input_m2": round(float(rng.uniform(9000, 26000)), 0),
                                     "yield_pct": round(y, 2), "scrap_reason": _scrap(rng, y)})

        # ---- sourcing for novel components (qualification timing relative to this launch) ----
        comp_feats = []
        for matnr, cat, novel, lead_w in bom:
            qty = float(rng.uniform(*CATEGORIES[cat][4]))
            if hero and cat == "FOAM_CORE":
                qty = 1032.0
            bom_rows.append({"MATNR_HDR": f"FG-{product}", "IDNRK": matnr, "MENGE_PER_1000M2": round(qty, 3),
                             "MEINS": CATEGORIES[cat][1], "POSNR": f"{(len(bom_rows) % 9 + 1) * 10:04d}",
                             "npi_id": npi_id})
            base = next(m["ZZ_BASE_WKLY_DEMAND"] for m in mat_rows if m["MATNR"] == matnr)
            req_peak_pilot = peak_m2 / (pilot_yield / 100) * qty / 1000
            req_peak_true = peak_m2 / (prod_yield / 100) * qty / 1000
            if novel:
                n_src = 1 if hero else int(rng.choice([1, 2, 3], p=[.45, .40, .15]))
                ids = ([sup_ids[0], sup_ids[1]] if hero
                       else list(rng.choice(sup_ids[2:], n_src, replace=False)))
                # capacity sized against PILOT-yield requirement (the planning flaw)
                tot_cap_factor = float(rng.lognormal(0.12, 0.22))
                for k, s in enumerate(ids):
                    # qualification timing: first source often ok, others may land after SOP
                    lag = rng.normal(-10 if k == 0 else -2, 7)
                    approved = sop + timedelta(weeks=float(lag))
                    if hero:
                        approved = date(2026, 9, 28) if k == 0 else date(2027, 6, 7)
                        if cat == "RELEASE_LINER" and k == 0:
                            approved = date(2026, 12, 21)
                    status = "QUALIFIED" if approved <= (TODAY if is_active else approved) else "PPAP_IN_PROGRESS"
                    if is_active and approved > TODAY:
                        status = "PPAP_IN_PROGRESS" if rng.random() < 0.7 or hero else "PILOT_ONLY"
                    share = 1.0 / len(ids)
                    cap = req_peak_pilot * tot_cap_factor * share
                    if hero:
                        if cat == "FOAM_CORE":
                            cap = 44_000.0 if k == 0 else 30_000.0
                        else:
                            cap = 60_000.0 if k == 0 else 38_000.0
                    src_rows.append({
                        "MATNR": matnr, "LIFNR": s, "QUAL_STATUS": status,
                        "PPAP_START": (approved - timedelta(weeks=int(rng.integers(10, 26)))).isoformat(),
                        "PPAP_APPROVED": approved.isoformat() if (not is_active or approved <= TODAY) else "",
                        "PPAP_PLANNED": approved.isoformat(),
                        "CAP_WKLY": round(cap, 1),
                        "LEAD_DAYS": lead_w * 7 + int(rng.integers(0, 15)),
                        "NETPR": round(next(m["STPRS"] for m in mat_rows if m["MATNR"] == matnr)
                                       * float(rng.uniform(1.0, 1.25)), 3), "WAERS": "USD",
                    })
            # ground-truth component features (same definitions the lakehouse pipeline uses)
            srcs = [r for r in src_rows if r["MATNR"] == matnr]
            # coverage: capacity from sources qualified by the ramp peak (SOP+8 wks) net of base-business draw
            qual_caps = [r["CAP_WKLY"] for r in srcs if date.fromisoformat(r["PPAP_PLANNED"]) <= sop + timedelta(weeks=8)]
            earliest_q = min(date.fromisoformat(r["PPAP_PLANNED"]) for r in srcs)
            avail = sum(qual_caps) - (0 if novel else base)
            cov_true = avail / req_peak_true if req_peak_true > 0 else 9
            qual_wait = max(0.0, (earliest_q - as_of).days / 7)
            # material gap: (lead time + remaining PPAP time) vs time until build-ahead start (SOP-8w).
            # Established materials are on contract with open POs -> not a gap driver.
            gap_w = ((min(lead_w, 30) + qual_wait) - (weeks_to_sop - 8)) if novel else -4.0
            comp_feats.append((cov_true, gap_w, len(qual_caps), novel))

            # open POs for active launches (display only)
            if is_active:
                for _ in range(int(rng.integers(1, 3))):
                    s = next((r["LIFNR"] for r in srcs), sup_ids[2])
                    po_rows.append({"EBELN": f"45{rng.integers(10_000_000, 99_999_999)}",
                                    "EBELP": "00010", "MATNR": matnr, "LIFNR": s, "WERKS": line_plant[line],
                                    "MENGE": round(req_peak_pilot * float(rng.uniform(2, 6)), 0),
                                    "MEINS": CATEGORIES[cat][1],
                                    "EINDT": (sop - timedelta(weeks=int(rng.integers(2, 12)))).isoformat(),
                                    "CONF_STATUS": rng.choice(["CONFIRMED", "UNCONFIRMED"], p=[.7, .3]),
                                    "npi_id": npi_id})

        min_cov = min(c[0] for c in comp_feats)
        worst_gap = max(c[1] for c in comp_feats)
        n_single = sum(1 for c in comp_feats if c[2] <= 1)
        n_unqual = sum(1 for c in comp_feats if c[2] == 0)

        # ---- outcome model (ground truth) ----
        short = max(0.0, 1 - min_cov)
        z = (-2.65 + 0.32 * max(0.0, worst_gap) + 3.4 * min(short, 0.8) + 0.11 * max(0.0, yield_gap - 6)
             + 6.0 * max(0.0, util_at_sop - 0.85) + 0.45 * n_unqual + 0.15 * n_single
             + (0.35 if seg == "EV_OEM" else 0) + rng.normal(0, 0.55))
        p_fail = float(_sigmoid(z))
        truth_rows.append({"npi_id": npi_id, "is_active": is_active, "p_fail_true": p_fail, "yield_gap_true": yield_gap,
                           "min_cov_true": min_cov, "worst_gap_true": worst_gap})

        launches.append({
            "npi_id": npi_id, "product_code": product, "product_name": product_name, "family_code": fam,
            "family_name": fname, "business_unit": "Bonding & Tapes", "market_segment": seg,
            "oem_customer": oem, "oem_program": program, "plant": line_plant[line], "production_line": line,
            "pilot_line": pilot_line, "sop_date": sop.isoformat(), "current_gate": current_gate,
            "launch_status": "ACTIVE" if is_active else "LAUNCHED",
            "complexity_layers": complexity, "novel_chemistry": novel_chem,
            "target_price_usd_m2": round(price, 2), "annual_volume_m2": round(annual_m2, 0),
            "year1_revenue_usd": round(year1_rev, 0), "program_lifetime_value_usd": round(lifetime_value, 0),
            "planned_line_utilization": round(util_at_sop, 3), "npi_manager": _manager(rng),
        })

        if not is_active:
            failed = rng.random() < p_fail
            slip = (2 + 0.7 * max(0.0, worst_gap) + 7 * min(short, 0.8) + rng.gamma(2, 1.4)) if failed \
                else max(0.0, rng.normal(0.3, 0.6))
            slip = round(float(slip), 1)
            otif = float(np.clip(rng.normal(0.72 if failed else 0.95, 0.07 if failed else 0.025), 0.35, 0.995))
            expedite = (year1_rev * 0.012 * slip + rng.lognormal(10.5, 0.6)) if failed else rng.lognormal(9.2, 0.7)
            eo = (rng.lognormal(11.6, 0.7) if failed else rng.lognormal(10.0, 0.8))
            platform_lost = bool(failed and seg in ("EV_OEM", "AUTO_TIER1") and slip >= 6 and rng.random() < 0.42)
            outcome_rows.append({
                "npi_id": npi_id, "sop_planned": sop.isoformat(),
                "sop_actual": (sop + timedelta(weeks=slip)).isoformat(), "slip_weeks": slip,
                "otif_first_90d": round(otif, 3), "expedite_cost_usd": round(float(expedite), 0),
                "eo_writeoff_usd": round(float(eo), 0), "deferred_revenue_usd": round(year1_rev * slip / 52, 0),
                "platform_lost": platform_lost,
                "lost_platform_value_usd": round(lifetime_value, 0) if platform_lost else 0.0,
                "root_cause_primary": _root_cause(rng, failed, short, worst_gap, yield_gap, util_at_sop),
                "postmortem_owner": "Commercialization Excellence",
            })

    # ---------------- assemble batch 1 ----------------
    materials = pd.DataFrame(mat_rows)
    source = pd.DataFrame(src_rows)
    source["CHANGED_AT"] = f"{BATCH1_DATE.isoformat()}T05:00:00"
    mes = pd.DataFrame(mes_rows)
    launches_df = pd.DataFrame(launches)
    batch1 = {
        "sap/MARA": materials,
        "sap/LFA1": suppliers,
        "sap/ZQM_SRC_QUAL": source,
        "sap/STPO": pd.DataFrame(bom_rows),
        "sap/EKPO": pd.DataFrame(po_rows),
        "mes/batch_runs": mes,
        "plm/npi_projects": launches_df,
        "plm/stage_gates": pd.DataFrame(gate_rows),
        "oem/demand_schedules": pd.DataFrame(demand_rows),
        "mfg/line_capacity": lines.merge(plants, on="WERKS"),
        "commercial/launch_outcomes": pd.DataFrame(outcome_rows),
        "ref/mitigation_playbook": pd.DataFrame(
            [{"action_type": a, "description": d, "effect_json": json.dumps(e), "typical_cost_usd": c}
             for a, d, e, c in MITIGATION_PLAYBOOK]),
    }

    # ---------------- batch 2: this morning's incremental drop ----------------
    hero_prod = "AFT-7200"
    trials = pd.DataFrame([
        {"run_id": "R990001", "line_id": "US20-F02", "plant": "US20", "product": hero_prod, "npi_id": "NPI-2027-014",
         "run_type": "PRODUCTION_TRIAL", "run_date": "2026-11-18", "input_m2": 14_200, "yield_pct": 72.8,
         "scrap_reason": "Foam core density variation / voids"},
        {"run_id": "R990002", "line_id": "US20-F02", "plant": "US20", "product": hero_prod, "npi_id": "NPI-2027-014",
         "run_type": "PRODUCTION_TRIAL", "run_date": "2026-11-20", "input_m2": 15_600, "yield_pct": 74.1,
         "scrap_reason": "Edge lift after lamination"},
    ])
    hero_mats = materials[materials.MAKTX.str.startswith("FC-220")].MATNR.tolist()
    upd = source[(source.MATNR.isin(hero_mats)) & (source.LIFNR == sup_ids[0])].copy()
    upd["CAP_WKLY"] = 40_000.0   # Arden capacity-allocation notice: FC-220 cut from 44k to 40k m2/wk
    upd["CHANGED_AT"] = f"{BATCH2_DATE.isoformat()}T05:00:00"
    batch2 = {"mes/batch_runs": trials, "sap/ZQM_SRC_QUAL": upd}

    return RawData(batch1=batch1, batch2=batch2, truth=pd.DataFrame(truth_rows))


def _scrap(rng, y):
    if y > 92:
        return ""
    return str(rng.choice(["Coat-weight variation", "Cure under-conversion", "Edge lift after lamination",
                           "Foam core density variation / voids", "Liner release force out of spec",
                           "Gels / contamination", "Web break"], p=[.24, .16, .14, .14, .12, .12, .08]))


def _manager(rng):
    first = ["Dana", "Priya", "Marcus", "Elena", "Tom", "Keiko", "Luis", "Grace", "Omar", "Hannah", "Victor", "Mei"]
    last = ["Lindgren", "Okoro", "Brandt", "Castillo", "Hughes", "Tanaka", "Moreno", "Fischer", "Haddad", "Novak",
            "Reyes", "Chen"]
    return f"{first[int(rng.integers(0, len(first)))]} {last[int(rng.integers(0, len(last)))]}"


def _root_cause(rng, failed, short, gap, ygap, util):
    if not failed:
        return "None - launched on plan"
    causes = {"Supplier capacity shortfall at ramp": short * 3,
              "Component qualification (PPAP) late vs SOP": max(0, gap) / 4,
              "Production yield below plan (pilot-to-line gap)": max(0, ygap - 6) / 4,
              "Coating line capacity conflict": max(0, util - 0.85) * 12,
              "OEM schedule change": 0.15}
    k = list(causes)
    w = np.array(list(causes.values())) + 1e-3
    return str(rng.choice(k, p=w / w.sum()))
