-- The CRM as the integration sees it: deals with HubSpot-style properties.
CREATE TABLE crm_deal (
    deal_id VARCHAR, bid_number VARCHAR, dealname VARCHAR, company VARCHAR, sector VARCHAR,
    amount_cents BIGINT, dealstage VARCHAR, closedate DATE, owner VARCHAR, updated_at TIMESTAMP
);
CREATE TABLE crm_sync_log (ts TIMESTAMP, direction VARCHAR, deal_id VARCHAR, actor VARCHAR, detail VARCHAR);

CREATE TABLE bid (
    bid_id VARCHAR, bid_number VARCHAR, deal_id VARCHAR, bid_name VARCHAR, sector VARCHAR,
    latest_revision INTEGER, created_at TIMESTAMP, created_by VARCHAR
);
-- Immutable. A price change is a new numbered revision; nothing here is updated
-- except is_latest, which moves to the newest.
CREATE TABLE bid_revision (
    bid_id VARCHAR, revision INTEGER, is_latest BOOLEAN, submitted_at TIMESTAMP, submitted_by VARCHAR,
    bid_name VARCHAR, bid_number VARCHAR, sector VARCHAR, client VARCHAR, gross_building_area_m2 INTEGER,
    site_establishment DATE, practical_completion DATE, submission_date DATE,
    direct_cents BIGINT, indirect_cents BIGINT, contingency_cents BIGINT, escalation_cents BIGINT,
    grand_total_cents BIGINT, margin_bp INTEGER, margin_cents BIGINT, final_ex_cents BIGINT,
    final_inc_cents BIGINT, rate_per_m2_cents BIGINT, warnings_acknowledged VARCHAR, data_json VARCHAR
);
CREATE TABLE bid_cost_line (
    bid_id VARCHAR, revision INTEGER, grid VARCHAR, line_no INTEGER, cost_code VARCHAR, description VARCHAR, amount_cents BIGINT
);
CREATE TABLE bid_competitor (bid_id VARCHAR, revision INTEGER, name VARCHAR, note VARCHAR);
