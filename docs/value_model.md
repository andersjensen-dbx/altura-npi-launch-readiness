# Value model: what the Control Tower is worth to Altura BTD

All inputs are from the synthetic data set and the executed notebooks (`notebooks/03_train_models.ipynb`,
`notebooks/04_score_launches.ipynb`). The structure is designed so Altura can replace each input with its own figures.

## Buyer KPIs
| Stakeholder | KPI this moves |
|---|---|
| **Executive sponsor**: Group President / Chief Supply Chain Officer | NPI revenue realization (new-product revenue share), OEM platform wins retained, expedite + E&O cost, first-90-day OTIF |
| **Domain owner**: VP Supply Chain / NPI Commercialization, Bonding & Tapes | Launches on-time to SOP, ramp OTIF, PPAP lead time, single-source exposure at SOP, time from risk signal to committed mitigation |

## 1 · Cost of the problem today (2025-26 holdout launches, margin view)
| Component | Basis | Per year |
|---|---|---|
| Expedite / premium freight | post-mortems | included below |
| E&O write-offs (pilot/pull-ahead material) | post-mortems | included below |
| Deferred revenue × 35% contribution margin | slip weeks × year-1 revenue / 52 | included below |
| Lost OEM platforms × 35% margin on lifetime revenue | design-in lost to competitor | included below |
| **Total failure cost** | 29 failed ramps of 107 launches | **$43.6M / yr** |

Historical context (2020-2026, 420 launches): **31.9%** of launches that passed pilot missed the ramp (slip > 2 wks or 90-day OTIF < 85%); **22 OEM platforms** were lost. The most common root cause is the pilot-to-production yield gap, followed by late component PPAP.

## 2 · What the model would have caught (back-test, temporal holdout)
- Flag the top 30% riskiest launches at G3: **66% of failed ramps caught**, precision **59%** vs a 27% base rate.
- **91% of total failure cost** sits in the flagged launches, so attention goes where the money is.
- **6 of 7** OEM platforms lost in 2025-26 would have been flagged ($144M lifetime revenue).

## 3 · Avoidable cost
Assumption: the mitigation playbook avoids **50%** of failure cost on flagged launches that would have failed. This is conservative: dual-sourcing and pull-ahead buys started 16+ weeks before SOP are routine levers when the signal arrives in time.

**≈ $19.8M per year avoidable** (margin view), plus the strategic value of retained platforms.

Sensitivity:

| Mitigation success | 30% | 50% | 70% |
|---|---|---|---|
| Avoidable / yr | $11.9M | $19.8M | $27.7M |

## 4 · Exposure in today's pipeline (36 launches past G3)
- **$57.3M** of **$170.0M** year-1 revenue at risk before mitigation (probability-weighted; 6 HIGH-risk launches).
- Three in-flight actions committed in Lakebase already reduce that to **$52.0M** (4 HIGH), so **$5.3M** is protected.
- **$57M** of OEM platform lifetime value at risk.
- **AFT-7200 / Northstar Motors NSM-EVX9** alone: **$17.1M** at risk (93%), with a $96M program. Committing the Mitigation Advisor's package (dual-source expedite + two pull-ahead buys + yield sprint) moved it from **93% to 15%** risk and protected **$14.4M**, measured end to end in 3.6 minutes (`notebooks/09_closed_loop_proof.ipynb`).

## 5 · Cost to run (order of magnitude, list price, to be sized with Lakemeter)
Serverless SDP daily refresh (minutes per day), scoring and briefs jobs, a Lakebase 1-CU autoscaling endpoint, a scale-to-zero serving endpoint, one Databricks App, Genie and FMAPI tokens. All are small, well under $150K/yr. **ROI > 100×** on the avoidable cost alone.

## 6 · Time to value
- Weeks 0-4: land SAP (MARA/LFA1/source list/BOM/PO), MES yields and PLM gates for BTD with Lakeflow Connect / existing SAP extracts; reuse this pipeline.
- Weeks 4-8: train on Altura's last 5 years of launch post-mortems; calibrate the playbook effects with supply-chain leads.
- Weeks 8-12: G3/G4 steering committee uses the Control Tower live on the next quarter's launches.
