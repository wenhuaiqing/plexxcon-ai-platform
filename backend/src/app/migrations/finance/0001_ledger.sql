-- A general ledger shaped like an accounting-system export: one signed line
-- per posting (debit positive, credit negative), every journal summing to zero.
CREATE TABLE gl_account (account_code VARCHAR, name VARCHAR, type VARCHAR, section VARCHAR, normal_side INTEGER, sort_order INTEGER);
CREATE TABLE gl_line (
    line_id BIGINT, journal_id VARCHAR, entity_id VARCHAR, posting_date DATE, account_code VARCHAR,
    amount_cents BIGINT, counterparty_id VARCHAR, project_id VARCHAR, description VARCHAR, source VARCHAR
);
