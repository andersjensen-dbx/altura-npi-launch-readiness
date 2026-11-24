-- =====================================================================================
-- GOLD: launch supply-readiness views that feed ML features, Genie, Lakebase and the app.
-- "as-of" date: active launches are evaluated as of ${as_of_date} (demo "today");
-- historical launches are evaluated as of their G3 (pilot validated / scale-up) gate,
-- i.e. what we would have known at the scale-up decision -> no label leakage.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_launch_yield_profile
COMMENT 'Per-launch yield evidence from MES: pilot-line yield, production-trial yield, realized first-12-week production yield (historical).' AS
SELECT npi_id,
  ROUND(AVG(CASE WHEN run_type = 'PILOT' THEN yield_pct END), 2)            AS pilot_yield_pct,
  COUNT(CASE WHEN run_type = 'PILOT' THEN 1 END)                            AS pilot_runs,
  ROUND(AVG(CASE WHEN run_type = 'PRODUCTION_TRIAL' THEN yield_pct END), 2) AS production_trial_yield_pct,
  COUNT(CASE WHEN run_type = 'PRODUCTION_TRIAL' THEN 1 END)                 AS production_trial_runs,
  ROUND(AVG(CASE WHEN run_type = 'PRODUCTION' THEN yield_pct END), 2)       AS realized_production_yield_pct,
  MAX(run_date)                                                             AS last_run_date
FROM silver_mes_batch_runs GROUP BY npi_id;

CREATE OR REFRESH MATERIALIZED VIEW gold_launch_portfolio
COMMENT 'One row per NPI launch: commercial context, SOP timing, line/pilot technology fit, yield evidence and (historical) outcomes. Grain: npi_id.' AS
WITH g3 AS (SELECT npi_id, MAX(CASE WHEN gate = 'G3' THEN gate_date END) AS g3_date FROM silver_stage_gates GROUP BY npi_id),
peak AS (SELECT npi_id, MAX(forecast_m2) AS peak_weekly_demand_m2,
                SUM(CASE WHEN week_rel_sop BETWEEN 0 AND 12 THEN forecast_m2 END) AS first_quarter_demand_m2
         FROM silver_oem_demand GROUP BY npi_id)
SELECT l.*, g3.g3_date,
  CASE WHEN l.launch_status = 'ACTIVE' THEN DATE '${as_of_date}' ELSE g3.g3_date END AS as_of_date,
  ROUND(datediff(l.sop_date, CASE WHEN l.launch_status = 'ACTIVE' THEN DATE '${as_of_date}' ELSE g3.g3_date END) / 7.0, 1) AS weeks_to_sop,
  peak.peak_weekly_demand_m2, peak.first_quarter_demand_m2,
  pl.technology AS production_line_technology, pp.technology AS pilot_line_technology,
  pl.region,
  2026 - pl.commissioned_year AS production_line_age_years,
  CASE WHEN (pp.technology = 'PILOT_UV' AND pl.technology = 'UV_CURE')
         OR (pp.technology = 'PILOT_SOLVENT' AND pl.technology IN ('SOLVENT_COAT', 'HOTMELT_COAT'))
       THEN 0 ELSE 1 END AS pilot_to_line_tech_mismatch,
  y.pilot_yield_pct, y.pilot_runs, y.production_trial_yield_pct, y.production_trial_runs,
  y.realized_production_yield_pct,
  o.slip_weeks, o.otif_first_90d, o.expedite_cost_usd, o.eo_writeoff_usd, o.deferred_revenue_usd,
  o.platform_lost, o.lost_platform_value_usd, o.root_cause_primary, o.ramp_failed
FROM silver_npi_launches l
LEFT JOIN g3 USING (npi_id)
LEFT JOIN peak USING (npi_id)
LEFT JOIN silver_coating_lines pl ON pl.line_id = l.production_line
LEFT JOIN silver_coating_lines pp ON pp.line_id = l.pilot_line
LEFT JOIN gold_launch_yield_profile y USING (npi_id)
LEFT JOIN silver_launch_outcomes o USING (npi_id);

CREATE OR REFRESH MATERIALIZED VIEW gold_launch_component_supply (
  CONSTRAINT has_requirement EXPECT (required_peak_weekly_at_pilot_yield > 0)
) COMMENT 'Supply readiness per launch x BOM component: ramp requirement at PILOT yield (how plans are built today), capacity qualified by the ramp peak (SOP+8 weeks) net of base-business draw, PPAP timing and material gap. Grain: npi_id, material_id.' AS
WITH q AS (
  SELECT b.npi_id, b.material_id,
    COUNT(*) AS n_approved_sources,
    COUNT(CASE WHEN s.ppap_planned_date <= date_add(p.sop_date, 56) THEN 1 END) AS n_sources_qualified_by_peak,
    COALESCE(SUM(CASE WHEN s.ppap_planned_date <= date_add(p.sop_date, 56) THEN s.qualified_weekly_capacity END), 0) AS capacity_qualified_by_peak,
    SUM(s.qualified_weekly_capacity) AS capacity_all_sources,
    MIN(s.ppap_planned_date) AS earliest_qualification_date,
    MAX(CASE WHEN s.ppap_planned_date > date_add(p.sop_date, 56) THEN s.ppap_planned_date END) AS latest_pending_qualification_date,
    MAX(sp.supplier_risk_tier) AS max_supplier_risk_tier,
    ARRAY_SORT(COLLECT_SET(CONCAT(sp.supplier_name, ' (', s.qualification_status, ')'))) AS sources
  FROM silver_bom b
  JOIN gold_launch_portfolio p USING (npi_id)
  LEFT JOIN silver_supplier_qualification s ON s.material_id = b.material_id
  LEFT JOIN silver_suppliers sp ON sp.supplier_id = s.supplier_id
  GROUP BY b.npi_id, b.material_id),
po AS (SELECT npi_id, material_id, SUM(po_qty) AS open_po_qty,
              COUNT(CASE WHEN confirmation_status = 'UNCONFIRMED' THEN 1 END) AS unconfirmed_po_lines
       FROM silver_purchase_orders GROUP BY npi_id, material_id)
SELECT b.npi_id, p.product_code, p.launch_status, b.material_id, m.material_desc, m.material_category, b.uom,
  m.is_novel_material, b.qty_per_1000_m2, m.lead_time_weeks, p.sop_date, p.as_of_date, p.weeks_to_sop,
  p.peak_weekly_demand_m2, p.pilot_yield_pct,
  ROUND(p.peak_weekly_demand_m2 / (p.pilot_yield_pct / 100) * b.qty_per_1000_m2 / 1000, 1) AS required_peak_weekly_at_pilot_yield,
  CASE WHEN m.is_novel_material THEN 0 ELSE m.base_business_weekly_demand END AS base_business_weekly_demand,
  q.capacity_qualified_by_peak, q.capacity_all_sources,
  ROUND(q.capacity_qualified_by_peak - CASE WHEN m.is_novel_material THEN 0 ELSE m.base_business_weekly_demand END, 1) AS capacity_available_for_launch,
  ROUND((q.capacity_qualified_by_peak - CASE WHEN m.is_novel_material THEN 0 ELSE m.base_business_weekly_demand END)
        / (p.peak_weekly_demand_m2 / (p.pilot_yield_pct / 100) * b.qty_per_1000_m2 / 1000), 3) AS coverage_at_pilot_yield,
  q.n_approved_sources, q.n_sources_qualified_by_peak, q.earliest_qualification_date, q.latest_pending_qualification_date,
  ROUND(GREATEST(0, datediff(q.earliest_qualification_date, p.as_of_date) / 7.0), 1) AS qualification_wait_weeks,
  CASE WHEN m.is_novel_material
       THEN ROUND(LEAST(m.lead_time_weeks, 30) + GREATEST(0, datediff(q.earliest_qualification_date, p.as_of_date) / 7.0)
                  - (p.weeks_to_sop - 8), 1)
       ELSE -4.0 END AS material_gap_weeks,
  q.max_supplier_risk_tier, q.sources, po.open_po_qty, po.unconfirmed_po_lines
FROM silver_bom b
JOIN gold_launch_portfolio p USING (npi_id)
JOIN silver_materials m USING (material_id)
JOIN q USING (npi_id, material_id)
LEFT JOIN po USING (npi_id, material_id);
