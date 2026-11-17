-- Shared by every feature: who exists, what jobs exist, and what happened.
CREATE TABLE entity (entity_id VARCHAR, name VARCHAR, description VARCHAR, is_group BOOLEAN);
CREATE TABLE project (
    project_id VARCHAR, name VARCHAR, client VARCHAR, sector VARCHAR, region VARCHAR,
    contract_value_cents BIGINT, start_date DATE, end_date DATE, status VARCHAR
);
-- Append-only. Refusals are recorded as well as changes.
CREATE TABLE audit_log (
    audit_id BIGINT, ts TIMESTAMP, actor VARCHAR, system VARCHAR, project_id VARCHAR, subject VARCHAR,
    action VARCHAR, outcome VARCHAR, detail VARCHAR, reason VARCHAR
);
CREATE TABLE kv (k VARCHAR, v VARCHAR);
