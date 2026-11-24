-- Governed business metrics (Unity Catalog metric views) shared by Genie, the app and BI.
-- ${catalog}/${schema} are substituted at deploy time.

CREATE OR REPLACE VIEW ${catalog}.${schema}.npi_launch_readiness_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: ${catalog}.${schema}.gold_launch_risk_scores
comment: "Launch-readiness KPIs for the ACTIVE NPI pipeline (launches past pilot, before SOP). One row per launch, scored daily and whenever a mitigation is committed."
dimensions:
  - name: Launch ID
    expr: npi_id
  - name: Product
    expr: product_name
    synonyms: ["product name", "tape", "SKU"]
  - name: Product Code
    expr: product_code
  - name: Product Family
    expr: family_name
  - name: Market Segment
    expr: market_segment
    comment: "EV_OEM, AUTO_TIER1, ELECTRONICS, INDUSTRIAL"
  - name: OEM Customer
    expr: oem_customer
    synonyms: ["customer", "OEM", "automaker"]
  - name: OEM Program
    expr: oem_program
    synonyms: ["vehicle program", "platform"]
  - name: Region
    expr: region
  - name: Plant
    expr: plant
  - name: Production Line
    expr: production_line
  - name: SOP Date
    expr: sop_date
    synonyms: ["start of production", "launch date"]
  - name: SOP Month
    expr: DATE_TRUNC('MONTH', sop_date)
  - name: SOP Quarter
    expr: "CONCAT(YEAR(sop_date), '-Q', QUARTER(sop_date))"
  - name: Current Gate
    expr: current_gate
    comment: "Stage gate: G3 = pilot validated / scale-up decision, G4 = launch readiness"
  - name: Risk Tier
    expr: risk_tier
    comment: "HIGH >= 60% ramp-failure probability, MEDIUM 25-60%, LOW < 25%"
  - name: NPI Manager
    expr: npi_manager
  - name: Binding Component
    expr: binding_component_desc
    comment: "BOM component with the lowest supply coverage at predicted production yield"
    synonyms: ["constrained material", "bottleneck material"]
  - name: Has Committed Mitigation
    expr: actions_applied > 0
measures:
  - name: Active Launches
    expr: COUNT(1)
  - name: High-Risk Launches
    expr: COUNT(1) FILTER (WHERE risk_tier = 'HIGH')
    synonyms: ["at-risk launches", "red launches"]
  - name: Share of Launches High Risk
    expr: "MEASURE(`High-Risk Launches`) / MEASURE(`Active Launches`)"
    format: {type: percentage}
  - name: Year-1 Revenue
    expr: SUM(year1_revenue_usd)
    format: {type: currency, currency_code: USD}
  - name: Revenue at Risk
    expr: SUM(revenue_at_risk_usd)
    comment: "Sum over launches of ramp-failure probability x year-1 revenue"
    format: {type: currency, currency_code: USD}
    synonyms: ["revenue exposure", "at-risk revenue"]
  - name: OEM Platform Value at Risk
    expr: SUM(platform_value_at_risk_usd)
    comment: "Probability-weighted lifetime revenue of OEM platforms that could be lost to a competitor if the ramp fails (auto & EV programs)"
    format: {type: currency, currency_code: USD}
  - name: Average Risk Score
    expr: AVG(risk_score)
    format: {type: percentage}
  - name: Average Baseline Risk Score
    expr: AVG(baseline_risk_score)
    comment: "Risk before committed mitigations"
    format: {type: percentage}
  - name: Risk Reduction from Mitigations
    expr: AVG(baseline_risk_score) - AVG(risk_score)
    format: {type: percentage}
  - name: Average Yield Gap (pts)
    expr: AVG(predicted_yield_gap_pts)
    comment: "Pilot yield minus predicted production yield, percentage points"
  - name: Launches with Supply Shortfall
    expr: COUNT(1) FILTER (WHERE min_coverage_at_predicted_yield < 1)
  - name: Launches with Material Gap
    expr: COUNT(1) FILTER (WHERE worst_material_gap_weeks > 0)
    comment: "Launches where a component's lead time + PPAP wait exceeds the time until build-ahead starts"
$$;

CREATE OR REPLACE VIEW ${catalog}.${schema}.npi_component_supply_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: ${catalog}.${schema}.gold_component_readiness
comment: "BOM component supply readiness for active NPI launches at predicted production yield. One row per launch x component."
dimensions:
  - name: Launch ID
    expr: npi_id
  - name: Product Code
    expr: product_code
  - name: Component
    expr: material_desc
    synonyms: ["material", "raw material"]
  - name: Material ID
    expr: material_id
  - name: Material Category
    expr: material_category
  - name: Unit of Measure
    expr: uom
  - name: Novel Material
    expr: is_novel_material
    comment: "New-to-BTD material introduced by this NPI (higher qualification risk)"
  - name: Readiness Status
    expr: readiness_status
    comment: "RED: coverage <90% or material gap >2 wks or no source qualified by ramp peak (SOP+8 wks); AMBER: coverage <110%, any gap, or single source"
  - name: Approved Sources
    expr: sources
measures:
  - name: Components
    expr: COUNT(1)
  - name: Red Components
    expr: COUNT(1) FILTER (WHERE readiness_status = 'RED')
  - name: Single-Sourced Components
    expr: COUNT(1) FILTER (WHERE n_sources_qualified_by_peak <= 1)
  - name: Components Without Qualified Source
    expr: COUNT(1) FILTER (WHERE n_sources_qualified_by_peak = 0)
  - name: Average Coverage at Predicted Yield
    expr: AVG(LEAST(coverage_at_predicted_yield, 5))
    comment: "Qualified weekly capacity / ramp-peak need at predicted yield (capped at 5x)"
  - name: Weekly Shortfall at Peak
    expr: SUM(weekly_shortfall_at_peak)
    comment: "Units per week short at ramp peak; only add up within one Unit of Measure"
  - name: Worst Material Gap (weeks)
    expr: MAX(material_gap_weeks)
$$;

CREATE OR REPLACE VIEW ${catalog}.${schema}.npi_launch_history_metrics
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: ${catalog}.${schema}.gold_launch_portfolio
filter: launch_status = 'LAUNCHED'
comment: "Outcomes of historical BTD NPI launches 2020-2026 (post-mortems): ramp failures, slip, OTIF, expedite, E&O, lost OEM platforms."
dimensions:
  - name: SOP Year
    expr: YEAR(sop_date)
  - name: Product Family
    expr: family_name
  - name: Market Segment
    expr: market_segment
  - name: OEM Customer
    expr: oem_customer
  - name: Plant
    expr: plant
  - name: Production Line
    expr: production_line
  - name: Root Cause
    expr: root_cause_primary
    synonyms: ["failure reason", "primary cause"]
  - name: Pilot-to-Line Technology Mismatch
    expr: pilot_to_line_tech_mismatch = 1
  - name: Novel Chemistry
    expr: novel_chemistry
measures:
  - name: Launches
    expr: COUNT(1)
  - name: Failed Ramps
    expr: COUNT(1) FILTER (WHERE ramp_failed)
    comment: "Slipped > 2 weeks or first-90-day OTIF < 85%"
  - name: Ramp Failure Rate
    expr: "MEASURE(`Failed Ramps`) / MEASURE(`Launches`)"
    format: {type: percentage}
  - name: Average Slip (weeks)
    expr: AVG(slip_weeks)
  - name: Average 90-Day OTIF
    expr: AVG(otif_first_90d)
    format: {type: percentage}
  - name: Expedite Cost
    expr: SUM(expedite_cost_usd)
    format: {type: currency, currency_code: USD}
  - name: E&O Write-off
    expr: SUM(eo_writeoff_usd)
    format: {type: currency, currency_code: USD}
  - name: Deferred Revenue
    expr: SUM(deferred_revenue_usd)
    format: {type: currency, currency_code: USD}
  - name: OEM Platforms Lost
    expr: COUNT(1) FILTER (WHERE platform_lost)
  - name: Lost Platform Lifetime Value
    expr: SUM(lost_platform_value_usd)
    format: {type: currency, currency_code: USD}
  - name: Average Pilot-to-Production Yield Gap (pts)
    expr: AVG(pilot_yield_pct - realized_production_yield_pct)
$$;
