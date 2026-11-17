-- Invoices reconcile at docket level. The four reconciliation columns are
-- written by services/msr_recon.py - one definition, in one place.
CREATE TABLE msr_invoice (
    invoice_id VARCHAR, project_id VARCHAR, register VARCHAR, supplier VARCHAR, invoice_no VARCHAR,
    invoice_date DATE, total_cents BIGINT, source_doc_id VARCHAR,
    expected_cents BIGINT, variance_bp INTEGER, open_lines INTEGER, recon_status VARCHAR,
    created_at TIMESTAMP, created_by VARCHAR, deleted_at TIMESTAMP, deleted_by VARCHAR
);
CREATE TABLE msr_invoice_line (
    invoice_id VARCHAR, line_no INTEGER, docket_no VARCHAR, description VARCHAR, qty_x100 BIGINT,
    rate_cents BIGINT, amount_cents BIGINT, docket_id VARCHAR, expected_cents BIGINT, match_status VARCHAR
);
