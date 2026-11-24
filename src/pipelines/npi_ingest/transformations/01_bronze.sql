-- =====================================================================================
-- BRONZE: raw, append-only ingestion of source-system extracts with Auto Loader.
-- One streaming table per extract; lineage columns capture file + ingest time.
-- Landing volume: /Volumes/<catalog>/<schema>/landing/<system>/<extract>/
-- =====================================================================================

CREATE OR REFRESH STREAMING TABLE bronze_sap_mara
COMMENT 'SAP material master (MARA/MAKT) extract - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/sap/MARA', format => 'csv', header => true,
  schemaHints => 'MATNR STRING, MAKTX STRING, MATKL STRING, MEINS STRING, PLIFZ INT, ZZ_NOVEL_FLAG STRING, ZZ_BASE_WKLY_DEMAND DOUBLE, STPRS DOUBLE');

CREATE OR REFRESH STREAMING TABLE bronze_sap_lfa1
COMMENT 'SAP vendor master (LFA1) extract - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/sap/LFA1', format => 'csv', header => true,
  schemaHints => 'LIFNR STRING, NAME1 STRING, LAND1 STRING, ZZ_RISK_TIER INT, ZZ_OTD_PCT DOUBLE');

CREATE OR REFRESH STREAMING TABLE bronze_sap_src_qual
COMMENT 'SAP custom ZQM_SRC_QUAL: approved source list + supplier PPAP qualification status & capacity. Arrives as full + incremental change records.' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/sap/ZQM_SRC_QUAL', format => 'csv', header => true,
  schemaHints => 'MATNR STRING, LIFNR STRING, QUAL_STATUS STRING, PPAP_START DATE, PPAP_APPROVED DATE, PPAP_PLANNED DATE, CAP_WKLY DOUBLE, LEAD_DAYS INT, NETPR DOUBLE, WAERS STRING, CHANGED_AT TIMESTAMP');

CREATE OR REFRESH STREAMING TABLE bronze_sap_stpo
COMMENT 'SAP BOM items (STPO) for NPI finished goods - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/sap/STPO', format => 'csv', header => true,
  schemaHints => 'MATNR_HDR STRING, IDNRK STRING, MENGE_PER_1000M2 DOUBLE, MEINS STRING, POSNR STRING, npi_id STRING');

CREATE OR REFRESH STREAMING TABLE bronze_sap_ekpo
COMMENT 'SAP open purchase order items (EKKO/EKPO) for NPI components - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/sap/EKPO', format => 'csv', header => true,
  schemaHints => 'EBELN STRING, EBELP STRING, MATNR STRING, LIFNR STRING, WERKS STRING, MENGE DOUBLE, MEINS STRING, EINDT DATE, CONF_STATUS STRING, npi_id STRING');

CREATE OR REFRESH STREAMING TABLE bronze_mes_batch_runs
COMMENT 'MES coating-line batch runs (pilot, production trial, production) - raw JSON lines' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/mes/batch_runs', format => 'json',
  schemaHints => 'run_id STRING, line_id STRING, plant STRING, product STRING, npi_id STRING, run_type STRING, run_date DATE, input_m2 DOUBLE, yield_pct DOUBLE, scrap_reason STRING');

CREATE OR REFRESH STREAMING TABLE bronze_plm_npi_projects
COMMENT 'PLM NPI project register - raw JSON lines' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/plm/npi_projects', format => 'json',
  schemaHints => 'sop_date DATE, complexity_layers INT, novel_chemistry BOOLEAN, annual_volume_m2 DOUBLE, year1_revenue_usd DOUBLE, program_lifetime_value_usd DOUBLE, planned_line_utilization DOUBLE, target_price_usd_m2 DOUBLE');

CREATE OR REFRESH STREAMING TABLE bronze_plm_stage_gates
COMMENT 'PLM stage-gate events G0-G5 - raw JSON lines' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/plm/stage_gates', format => 'json', schemaHints => 'gate_date DATE');

CREATE OR REFRESH STREAMING TABLE bronze_oem_demand
COMMENT 'OEM program demand schedules (EDI DELFOR-style weekly forecast) - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/oem/demand_schedules', format => 'csv', header => true,
  schemaHints => 'week_start DATE, week_rel_sop INT, forecast_m2 DOUBLE');

CREATE OR REFRESH STREAMING TABLE bronze_mfg_line_capacity
COMMENT 'Coating line master: technology, capacity, utilization - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/mfg/line_capacity', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_launch_outcomes
COMMENT 'Commercialization post-mortems of historical launches (slip, OTIF, expedite, E&O, platform loss) - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/commercial/launch_outcomes', format => 'csv', header => true,
  schemaHints => 'sop_planned DATE, sop_actual DATE, slip_weeks DOUBLE, otif_first_90d DOUBLE, platform_lost BOOLEAN');

CREATE OR REFRESH STREAMING TABLE bronze_mitigation_playbook
COMMENT 'Supply-chain mitigation playbook reference (action types and modeled effects) - raw' AS
SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${landing}/ref/mitigation_playbook', format => 'csv', header => true, multiLine => true, escape => '"');
