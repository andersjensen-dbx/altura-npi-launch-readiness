-- =====================================================================================
-- SILVER: conformed, business-named, quality-checked entities.
-- Supplier qualification is tracked as SCD Type 2 (Auto CDC) so PPAP slips and
-- capacity notices are auditable over time.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW silver_materials (
  CONSTRAINT material_id_present EXPECT (material_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT lead_time_positive EXPECT (lead_time_days > 0)
) COMMENT 'Raw-material master for adhesives & tapes (monomers, foam cores, liners, fillers, films). One row per material.' AS
SELECT MATNR AS material_id, MAKTX AS material_desc, MATKL AS material_category, MEINS AS uom,
       PLIFZ AS lead_time_days, ROUND(PLIFZ / 7.0, 1) AS lead_time_weeks,
       (ZZ_NOVEL_FLAG = 'X') AS is_novel_material,
       ZZ_BASE_WKLY_DEMAND AS base_business_weekly_demand, STPRS AS standard_cost
FROM bronze_sap_mara
QUALIFY row_number() OVER (PARTITION BY MATNR ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW silver_suppliers (
  CONSTRAINT supplier_id_present EXPECT (supplier_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT risk_tier_valid EXPECT (supplier_risk_tier BETWEEN 1 AND 5)
) COMMENT 'Supplier master with risk tier (1=low..5=high) and trailing on-time-delivery %.' AS
SELECT LIFNR AS supplier_id, NAME1 AS supplier_name, LAND1 AS supplier_country,
       ZZ_RISK_TIER AS supplier_risk_tier, ZZ_OTD_PCT AS supplier_otd_pct
FROM bronze_sap_lfa1
QUALIFY row_number() OVER (PARTITION BY LIFNR ORDER BY _ingested_at DESC) = 1;

-- ---- supplier qualification: SCD2 history via Auto CDC ----
CREATE TEMPORARY VIEW src_qual_changes AS
SELECT MATNR AS material_id, LIFNR AS supplier_id, QUAL_STATUS AS qualification_status,
       PPAP_START AS ppap_start_date, PPAP_APPROVED AS ppap_approved_date, PPAP_PLANNED AS ppap_planned_date,
       CAP_WKLY AS qualified_weekly_capacity, LEAD_DAYS AS supplier_lead_time_days,
       NETPR AS unit_price, WAERS AS currency, CHANGED_AT AS changed_at
FROM STREAM(bronze_sap_src_qual);

CREATE OR REFRESH STREAMING TABLE silver_supplier_qualification_history
COMMENT 'SCD Type 2 history of approved-source / PPAP qualification records per (material, supplier). Current rows: __END_AT IS NULL.';

CREATE FLOW src_qual_cdc AS AUTO CDC INTO silver_supplier_qualification_history
FROM STREAM(src_qual_changes)
KEYS (material_id, supplier_id)
SEQUENCE BY changed_at
STORED AS SCD TYPE 2;

CREATE OR REFRESH MATERIALIZED VIEW silver_supplier_qualification (
  CONSTRAINT capacity_non_negative EXPECT (qualified_weekly_capacity >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT status_valid EXPECT (qualification_status IN ('QUALIFIED', 'PPAP_IN_PROGRESS', 'PILOT_ONLY')),
  CONSTRAINT approved_has_date EXPECT (qualification_status <> 'QUALIFIED' OR ppap_approved_date IS NOT NULL)
) COMMENT 'Current approved-source / PPAP qualification state per (material, supplier): status, planned approval date, weekly capacity available to Altura, lead time, price.' AS
SELECT * EXCEPT (__START_AT, __END_AT), __START_AT AS valid_from
FROM silver_supplier_qualification_history WHERE __END_AT IS NULL;

CREATE OR REFRESH MATERIALIZED VIEW silver_bom (
  CONSTRAINT qty_positive EXPECT (qty_per_1000_m2 > 0) ON VIOLATION DROP ROW
) COMMENT 'Bill of materials for NPI finished goods: component quantity per 1,000 m2 of finished tape.' AS
SELECT npi_id, replace(MATNR_HDR, 'FG-', '') AS product_code, IDNRK AS material_id,
       MENGE_PER_1000M2 AS qty_per_1000_m2, MEINS AS uom, POSNR AS bom_item
FROM bronze_sap_stpo;

CREATE OR REFRESH MATERIALIZED VIEW silver_purchase_orders
COMMENT 'Open purchase-order lines for NPI components with delivery date and supplier confirmation status.' AS
SELECT EBELN AS po_number, EBELP AS po_item, npi_id, MATNR AS material_id, LIFNR AS supplier_id,
       WERKS AS plant, MENGE AS po_qty, MEINS AS uom, EINDT AS delivery_date, CONF_STATUS AS confirmation_status
FROM bronze_sap_ekpo;

CREATE OR REFRESH STREAMING TABLE silver_mes_batch_runs (
  CONSTRAINT yield_in_range EXPECT (yield_pct BETWEEN 0 AND 100) ON VIOLATION DROP ROW,
  CONSTRAINT input_positive EXPECT (input_m2 > 0) ON VIOLATION DROP ROW,
  CONSTRAINT known_run_type EXPECT (run_type IN ('PILOT', 'PRODUCTION_TRIAL', 'PRODUCTION'))
) COMMENT 'Coating-line batch runs with yield %. PILOT = pilot line, PRODUCTION_TRIAL = scale-up trial on the production line, PRODUCTION = post-SOP runs.' AS
SELECT run_id, npi_id, product AS product_code, line_id, plant, run_type, run_date, input_m2,
       yield_pct, ROUND(input_m2 * yield_pct / 100, 0) AS good_output_m2, nullif(scrap_reason, '') AS scrap_reason
FROM STREAM(bronze_mes_batch_runs);

CREATE OR REFRESH MATERIALIZED VIEW silver_npi_launches (
  CONSTRAINT npi_id_present EXPECT (npi_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT sop_present EXPECT (sop_date IS NOT NULL)
) COMMENT 'NPI launch register (PLM): product, OEM customer/program, plant/line, SOP date, gate, revenue and program value.' AS
SELECT npi_id, product_code, product_name, family_code, family_name, business_unit, market_segment,
       oem_customer, oem_program, plant, production_line, pilot_line, sop_date, current_gate, launch_status,
       complexity_layers, novel_chemistry, target_price_usd_m2, annual_volume_m2, year1_revenue_usd,
       program_lifetime_value_usd, planned_line_utilization, npi_manager
FROM bronze_plm_npi_projects
QUALIFY row_number() OVER (PARTITION BY npi_id ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW silver_stage_gates
COMMENT 'Stage-gate history per NPI (G0 Idea -> G5 SOP).' AS
SELECT npi_id, gate, gate_name, gate_date, decision, approver_role, nullif(notes, '') AS notes FROM bronze_plm_stage_gates;

CREATE OR REFRESH MATERIALIZED VIEW silver_oem_demand (
  CONSTRAINT forecast_non_negative EXPECT (forecast_m2 >= 0) ON VIOLATION DROP ROW
) COMMENT 'Weekly OEM program demand forecast (m2) from SOP-8 to SOP+26 weeks.' AS
SELECT npi_id, customer AS oem_customer, program AS oem_program, product AS product_code, week_start,
       week_rel_sop, forecast_m2, forecast_version
FROM bronze_oem_demand;

CREATE OR REFRESH MATERIALIZED VIEW silver_coating_lines
COMMENT 'Coating / converting lines: plant, technology, weekly capacity (m2), base utilization.' AS
SELECT LINE_ID AS line_id, WERKS AS plant, PLANT_NAME AS plant_name, LOCATION AS plant_location, REGION AS region,
       TECHNOLOGY AS technology, CAST(CAPACITY_M2_WK AS DOUBLE) AS capacity_m2_per_week,
       CAST(COMMISSIONED_YEAR AS INT) AS commissioned_year, CAST(BASE_UTILIZATION AS DOUBLE) AS base_utilization
FROM bronze_mfg_line_capacity;

CREATE OR REFRESH MATERIALIZED VIEW silver_launch_outcomes (
  CONSTRAINT otif_valid EXPECT (otif_first_90d BETWEEN 0 AND 1)
) COMMENT 'Historical launch outcomes. ramp_failed = slipped >2 weeks or first-90-day OTIF < 85%.' AS
SELECT npi_id, sop_planned, sop_actual, slip_weeks, otif_first_90d,
       CAST(expedite_cost_usd AS DOUBLE) AS expedite_cost_usd, CAST(eo_writeoff_usd AS DOUBLE) AS eo_writeoff_usd,
       CAST(deferred_revenue_usd AS DOUBLE) AS deferred_revenue_usd, platform_lost,
       CAST(lost_platform_value_usd AS DOUBLE) AS lost_platform_value_usd, root_cause_primary,
       (slip_weeks > 2 OR otif_first_90d < 0.85) AS ramp_failed
FROM bronze_launch_outcomes;

CREATE OR REFRESH MATERIALIZED VIEW silver_mitigation_playbook
COMMENT 'Mitigation playbook: action types the Control Tower can recommend and their modeled effect on launch risk drivers.' AS
SELECT action_type, description, effect_json, CAST(typical_cost_usd AS DOUBLE) AS typical_cost_usd
FROM bronze_mitigation_playbook;
