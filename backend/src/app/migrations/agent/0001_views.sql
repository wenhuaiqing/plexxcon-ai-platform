-- The data agent's whole world: these views, and nothing else. Dollars not
-- cents, deleted rows already excluded, so a plain question gets a plain query.
CREATE VIEW v_project AS
SELECT project_id AS job_number, name, client, sector, region, round(contract_value_cents / 100.0, 2) AS contract_value,
       start_date, end_date, status
FROM project;

CREATE VIEW v_gl AS
SELECT l.entity_id, e.name AS entity_name, l.posting_date,
       CASE WHEN month(l.posting_date) >= 7 THEN year(l.posting_date) + 1 ELSE year(l.posting_date) END AS fin_year,
       date_trunc('month', l.posting_date)::DATE AS period, l.account_code, a.name AS account_name, a.type AS account_type,
       a.section, round(l.amount_cents / 100.0, 2) AS amount_debit_positive, l.counterparty_id, l.project_id AS job_number,
       l.description, l.source
FROM gl_line l JOIN gl_account a USING (account_code) JOIN entity e USING (entity_id);

-- Revenue and other income positive, costs positive: the way a P&L reads.
CREATE VIEW v_pnl_monthly AS
SELECT l.entity_id, date_trunc('month', l.posting_date)::DATE AS period,
       CASE WHEN month(l.posting_date) >= 7 THEN year(l.posting_date) + 1 ELSE year(l.posting_date) END AS fin_year,
       a.section, l.account_code, a.name AS account_name, a.type AS account_type,
       (l.counterparty_id IS NOT NULL AND l.counterparty_id IN (SELECT entity_id FROM entity WHERE is_group)) AS is_intercompany,
       round(sum(CASE WHEN a.type IN ('revenue', 'other_income') THEN -l.amount_cents ELSE l.amount_cents END) / 100.0, 2) AS amount
FROM gl_line l JOIN gl_account a USING (account_code)
WHERE a.type IN ('revenue', 'other_income', 'cogs', 'expense')
GROUP BY ALL;

-- Closing balance of every balance sheet account at each month end, natural sign.
CREATE VIEW v_balance_sheet AS
WITH months AS (SELECT DISTINCT last_day(posting_date) AS month_end FROM gl_line)
SELECT l.entity_id, m.month_end, a.section, l.account_code, a.name AS account_name, a.type AS account_type,
       round(sum(l.amount_cents * a.normal_side) / 100.0, 2) AS balance
FROM months m JOIN gl_line l ON l.posting_date <= m.month_end JOIN gl_account a USING (account_code)
WHERE a.type IN ('asset', 'liability', 'equity')
GROUP BY ALL;

-- What each entity says it is owed by, and owes to, each related party.
CREATE VIEW v_related_party_balance AS
WITH months AS (SELECT DISTINCT last_day(posting_date) AS month_end FROM gl_line)
SELECT l.entity_id, l.counterparty_id, m.month_end,
       round(sum(CASE WHEN l.account_code = '1800' THEN l.amount_cents ELSE 0 END) / 100.0, 2) AS receivable,
       round(sum(CASE WHEN l.account_code = '2800' THEN -l.amount_cents ELSE 0 END) / 100.0, 2) AS payable
FROM months m JOIN gl_line l ON l.posting_date <= m.month_end
WHERE l.account_code IN ('1800', '2800')
GROUP BY ALL;

CREATE VIEW v_crm_deal AS
SELECT deal_id, bid_number, dealname, company, sector, round(amount_cents / 100.0, 2) AS amount, dealstage, closedate, owner FROM crm_deal;

CREATE VIEW v_bid_revision AS
SELECT r.bid_id, r.bid_number, r.bid_name, r.revision, r.is_latest, r.submitted_at, r.submitted_by, r.sector, r.client,
       r.gross_building_area_m2, r.site_establishment, r.practical_completion, r.submission_date,
       round(r.direct_cents / 100.0, 2) AS direct_cost, round(r.indirect_cents / 100.0, 2) AS indirect_cost,
       round(r.grand_total_cents / 100.0, 2) AS grand_total, round(r.margin_bp / 100.0, 2) AS margin_pct, round(r.margin_cents / 100.0, 2) AS margin,
       round(r.final_ex_cents / 100.0, 2) AS final_excl_tax, round(r.final_inc_cents / 100.0, 2) AS final_incl_tax,
       round(r.rate_per_m2_cents / 100.0, 2) AS rate_per_m2, d.dealstage AS crm_stage
FROM bid_revision r JOIN bid b USING (bid_id) LEFT JOIN crm_deal d ON d.deal_id = b.deal_id;

CREATE VIEW v_bid_cost_line AS
SELECT c.bid_id, r.bid_number, c.revision, r.is_latest, c.grid, c.cost_code, c.description, round(c.amount_cents / 100.0, 2) AS amount
FROM bid_cost_line c JOIN bid_revision r USING (bid_id, revision);

CREATE VIEW v_rate_library AS
SELECT rate_code, trade, task, unit, round(rate_x1000 / 1000.0, 3) AS units_per_worker_hour, default_crew FROM tp_rate;

CREATE VIEW v_trade_request AS
SELECT request_id, version, project_id AS job_number, title, status, author, submitted_at, reviewer, reviewed_at,
       round(total_hours_x100 / 100.0, 2) AS labour_hours, round(labour_cents / 100.0, 2) AS labour_cost,
       round(non_production_cents / 100.0, 2) AS non_production_cost, round(materials_cents / 100.0, 2) AS materials_cost,
       round(plant_cents / 100.0, 2) AS plant_cost, round(total_cents / 100.0, 2) AS total_budget, peak_crew, target_finish, finish_date, on_time
FROM tp_request;

CREATE VIEW v_trade_request_trade AS
SELECT t.request_id, q.project_id AS job_number, q.status, t.trade, t.mobilisation, t.crew_size,
       round(t.hours_x100 / 100.0, 2) AS labour_hours, round(t.overtime_hours_x100 / 100.0, 2) AS overtime_hours, t.work_days,
       t.start_date, t.finish_date, t.target_finish, t.on_time, round(t.labour_cents / 100.0, 2) AS labour_cost
FROM tp_request_trade t JOIN tp_request q USING (request_id);

-- register is 'concrete' (unit m3) or 'reo' (unit t). Never add quantities across the two.
CREATE VIEW v_msr_budget AS
SELECT b.line_id, b.project_id AS job_number, b.register, b.element, b.sub_element, b.unit,
       round(b.budget_qty_x100 / 100.0, 2) AS budget_qty, round(b.budget_rate_cents / 100.0, 2) AS budget_rate,
       round(b.budget_qty_x100 * b.budget_rate_cents / 10000.0, 2) AS budget_amount,
       round(b.fac_qty_x100 / 100.0, 2) AS fac_qty, round(b.fac_rate_cents / 100.0, 2) AS fac_rate,
       round(b.fac_qty_x100 * b.fac_rate_cents / 10000.0, 2) AS fac_amount,
       coalesce(d.delivered_qty, 0) AS delivered_qty
FROM msr_budget_line b
LEFT JOIN (SELECT v.line_id, round(sum(k.qty_x100) / 100.0, 2) AS delivered_qty
           FROM msr_docket k JOIN msr_delivery v USING (delivery_id)
           WHERE k.deleted_at IS NULL AND v.deleted_at IS NULL GROUP BY v.line_id) d USING (line_id)
WHERE b.deleted_at IS NULL;

CREATE VIEW v_msr_delivery AS
SELECT v.delivery_id, v.project_id AS job_number, v.register, v.line_id, v.description, v.supplier, v.item,
       v.scheduled_date, round(v.planned_qty_x100 / 100.0, 2) AS planned_qty,
       round(coalesce(sum(k.qty_x100), 0) / 100.0, 2) AS delivered_qty, count(k.docket_id) AS dockets,
       CASE WHEN count(k.docket_id) > 0 THEN 'delivered' ELSE 'scheduled' END AS status
FROM msr_delivery v LEFT JOIN msr_docket k ON k.delivery_id = v.delivery_id AND k.deleted_at IS NULL
WHERE v.deleted_at IS NULL
GROUP BY ALL;

CREATE VIEW v_msr_docket AS
SELECT docket_id, delivery_id, project_id AS job_number, register, docket_no, delivered_date, item, round(qty_x100 / 100.0, 2) AS qty
FROM msr_docket WHERE deleted_at IS NULL;

-- recon_status: green = allocated and balanced; amber = 1 to 5 percent out or an
-- open line; red = more than 5 percent out.
CREATE VIEW v_msr_invoice AS
SELECT invoice_id, project_id AS job_number, register, supplier, invoice_no, invoice_date,
       round(total_cents / 100.0, 2) AS invoiced_amount, round(expected_cents / 100.0, 2) AS expected_amount,
       round((total_cents - expected_cents) / 100.0, 2) AS variance_amount, round(variance_bp / 100.0, 2) AS variance_pct,
       open_lines, recon_status
FROM msr_invoice WHERE deleted_at IS NULL;

CREATE VIEW v_msr_price AS
SELECT project_id AS job_number, register, supplier, kind, item, unit, round(rate_cents / 100.0, 2) AS rate, waived,
       effective_from, effective_to
FROM msr_price WHERE deleted_at IS NULL;
