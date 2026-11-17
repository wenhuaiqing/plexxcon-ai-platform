-- Project-scoped: nothing is visible for a job until it is enrolled.
CREATE TABLE msr_enrolment (project_id VARCHAR, enrolled_at TIMESTAMP, enrolled_by VARCHAR);
-- register is 'concrete' (m3) or 'reo' (t). Quantities of the two are never summed.
-- Budget is the locked contract baseline; forecast at completion (FAC) is live.
CREATE TABLE msr_budget_line (
    line_id VARCHAR, project_id VARCHAR, register VARCHAR, element VARCHAR, sub_element VARCHAR, unit VARCHAR,
    budget_qty_x100 BIGINT, budget_rate_cents BIGINT, fac_qty_x100 BIGINT, fac_rate_cents BIGINT,
    created_at TIMESTAMP, created_by VARCHAR, deleted_at TIMESTAMP, deleted_by VARCHAR
);
-- Rates carry effective dates, so an old and a new price coexist.
CREATE TABLE msr_price (
    price_id VARCHAR, project_id VARCHAR, register VARCHAR, supplier VARCHAR, kind VARCHAR, item VARCHAR,
    unit VARCHAR, rate_cents BIGINT, waived BOOLEAN, effective_from DATE, effective_to DATE,
    source_doc_id VARCHAR, created_at TIMESTAMP, created_by VARCHAR, deleted_at TIMESTAMP, deleted_by VARCHAR
);
-- Concrete: one pour is one delivery event. Reo: one bar schedule.
CREATE TABLE msr_delivery (
    delivery_id VARCHAR, project_id VARCHAR, register VARCHAR, line_id VARCHAR, description VARCHAR,
    supplier VARCHAR, item VARCHAR, scheduled_date DATE, planned_qty_x100 BIGINT,
    created_at TIMESTAMP, created_by VARCHAR, deleted_at TIMESTAMP, deleted_by VARCHAR
);
CREATE TABLE msr_docket (
    docket_id VARCHAR, delivery_id VARCHAR, project_id VARCHAR, register VARCHAR, docket_no VARCHAR,
    delivered_date DATE, item VARCHAR, qty_x100 BIGINT, source_doc_id VARCHAR,
    created_at TIMESTAMP, created_by VARCHAR, deleted_at TIMESTAMP, deleted_by VARCHAR
);
