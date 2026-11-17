-- One shared library every task draws its production rate from.
CREATE TABLE tp_rate (
    rate_code VARCHAR, trade VARCHAR, trade_code VARCHAR, task VARCHAR, unit VARCHAR,
    rate_x1000 INTEGER, default_crew INTEGER, updated_at TIMESTAMP, updated_by VARCHAR
);
-- A request is versioned: revising one makes a new row with the same root.
-- The numbers stored are the server's, calculated at save.
CREATE TABLE tp_request (
    request_id VARCHAR, root_request_id VARCHAR, version INTEGER, project_id VARCHAR, title VARCHAR,
    status VARCHAR, author VARCHAR, created_at TIMESTAMP, updated_at TIMESTAMP, submitted_at TIMESTAMP,
    reviewer VARCHAR, reviewed_at TIMESTAMP, feedback VARCHAR, data_json VARCHAR,
    total_hours_x100 BIGINT, labour_cents BIGINT, non_production_cents BIGINT, materials_cents BIGINT,
    plant_cents BIGINT, total_cents BIGINT, peak_crew INTEGER, target_finish DATE, finish_date DATE, on_time BOOLEAN
);
CREATE TABLE tp_request_trade (
    request_id VARCHAR, trade VARCHAR, trade_code VARCHAR, mobilisation VARCHAR, classification VARCHAR,
    crew_size INTEGER, hours_x100 BIGINT, ordinary_hours_x100 BIGINT, overtime_hours_x100 BIGINT,
    work_days INTEGER, start_date DATE, finish_date DATE, target_finish DATE, on_time BOOLEAN, labour_cents BIGINT
);
CREATE TABLE tp_request_task (
    request_id VARCHAR, trade VARCHAR, seq INTEGER, cost_code VARCHAR, location VARCHAR, task VARCHAR,
    rate_code VARCHAR, unit VARCHAR, quantity_x100 BIGINT, rate_x1000 INTEGER, modifier_x10000 INTEGER, hours_x100 BIGINT
);
