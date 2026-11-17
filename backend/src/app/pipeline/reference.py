"""Everything the generator invents, declared once.

All of it is synthetic. The group, its entities, jobs, clients, suppliers,
rates and ledgers are made up for a demonstration; none of it describes a real
business. Assumptions are named as assumptions.

Every defect the generator seeds is declared in SEEDED below. Tests assert
that each one is found from the data by the services - never by reading this
file - so the reconciliation and the mirror check are proven, not asserted.
"""

from __future__ import annotations

from datetime import date, datetime

SEED = 20261117

# The demo's clock. Finance is closed to the end of October; the workflow
# systems are "today" on the Monday after.
DEMO_TODAY = date(2026, 11, 16)
DEMO_NOW = datetime(2026, 11, 16, 8, 30)
LEDGER_START = date(2025, 7, 1)
LEDGER_END = date(2026, 10, 31)
FY_START_MONTH = 7  # Australian financial year: 1 July to 30 June

# ---------------------------------------------------------------- entities --
# An assumption, made so related-party reporting has something to report: a
# small private construction group. Not a statement about any real group.
ENTITIES = [
    ("HOLD", "Group Holdings Pty Ltd", "Holding company"),
    ("CON", "Construction Pty Ltd", "Builder - holds every construction contract"),
    ("PLT", "Plant & Equipment Pty Ltd", "Owns plant, hires it to the builder"),
    ("PROP", "Property Trust", "Owns the office and yard, leases them to the builder"),
]
GROUP_ENTITY_IDS = [e[0] for e in ENTITIES]
# A related party that is not a group entity: never eliminated on consolidation.
RELATED_NON_GROUP = [("DIR", "Directors' loan accounts")]

# account_code, name, type, section, normal side (+1 debit, -1 credit)
ACCOUNTS = [
    ("1000", "Cash at bank", "asset", "Current assets", 1),
    ("1100", "Trade debtors", "asset", "Current assets", 1),
    ("1150", "Retentions receivable", "asset", "Current assets", 1),
    ("1300", "Prepayments", "asset", "Current assets", 1),
    ("1800", "Related party receivables", "asset", "Current assets", 1),
    ("1500", "Plant and equipment at cost", "asset", "Non-current assets", 1),
    ("1510", "Accumulated depreciation", "asset", "Non-current assets", 1),
    ("1600", "Land and buildings", "asset", "Non-current assets", 1),
    ("2000", "Trade creditors", "liability", "Current liabilities", -1),
    ("2200", "Payroll liabilities", "liability", "Current liabilities", -1),
    ("2800", "Related party payables", "liability", "Current liabilities", -1),
    ("2300", "Bank loans", "liability", "Non-current liabilities", -1),
    ("3000", "Issued capital", "equity", "Equity", -1),
    ("3100", "Retained earnings", "equity", "Equity", -1),
    ("4000", "Contract revenue", "revenue", "Revenue", -1),
    ("4100", "Variations revenue", "revenue", "Revenue", -1),
    ("4800", "Related party revenue", "revenue", "Revenue", -1),
    ("4900", "Interest income", "other_income", "Other income", -1),
    ("5000", "Subcontractors", "cogs", "Cost of sales", 1),
    ("5100", "Materials", "cogs", "Cost of sales", 1),
    ("5200", "Site labour", "cogs", "Cost of sales", 1),
    ("5300", "Plant hire - external", "cogs", "Cost of sales", 1),
    ("5310", "Plant hire - related party", "cogs", "Cost of sales", 1),
    ("6000", "Salaries and wages", "expense", "Overheads", 1),
    ("6100", "Rent - related party", "expense", "Overheads", 1),
    ("6110", "Management fees - related party", "expense", "Overheads", 1),
    ("6200", "Insurance", "expense", "Overheads", 1),
    ("6300", "Motor vehicles", "expense", "Overheads", 1),
    ("6400", "IT and software", "expense", "Overheads", 1),
    ("6500", "Depreciation", "expense", "Overheads", 1),
    ("6600", "Interest expense", "expense", "Overheads", 1),
    ("6900", "Other overheads", "expense", "Overheads", 1),
]
RP_RECEIVABLE, RP_PAYABLE, RP_REVENUE = "1800", "2800", "4800"
RP_EXPENSE_ACCOUNTS = ["5310", "6100", "6110"]

# ----------------------------------------------------------------- projects --
# job_number, name, client, sector, region, contract value ($), start, end, status
PROJECTS = [
    ("2401", "Seaview Towers facade remediation", "Body Corporate for Seaview Towers", "Remedial", "Gold Coast", 4_850_000, date(2025, 8, 4), date(2026, 9, 25), "complete"),
    ("2407", "Northgate cold store slab replacement", "Northgate Cold Storage Pty Ltd", "Industrial", "Brisbane", 3_120_000, date(2025, 10, 13), date(2026, 6, 26), "complete"),
    ("2412", "Riverbend apartments balcony rectification", "Body Corporate for Riverbend Apartments", "Body corporate", "Brisbane", 2_640_000, date(2025, 11, 3), date(2026, 12, 18), "active"),
    ("2418", "Harbour Road warehouse extension", "Harbour Road Logistics Pty Ltd", "Industrial", "Brisbane", 7_900_000, date(2026, 2, 2), date(2027, 2, 26), "active"),
    ("2423", "Kirra Point carpark concrete repair", "Body Corporate for Kirra Point", "Remedial", "Gold Coast", 1_980_000, date(2026, 3, 16), date(2026, 12, 4), "active"),
    ("2427", "Eagle Farm food plant upgrade", "Eastside Foods Pty Ltd", "Industrial", "Brisbane", 6_450_000, date(2026, 4, 20), date(2027, 4, 30), "active"),
    ("2431", "Maroochy medical centre fitout and extension", "Coastline Health Property Trust", "Commercial", "Sunshine Coast", 5_300_000, date(2026, 6, 1), date(2027, 5, 28), "active"),
    ("2436", "Palm Court roof and membrane renewal", "Body Corporate for Palm Court", "Body corporate", "Sunshine Coast", 1_450_000, date(2026, 7, 13), date(2027, 1, 29), "active"),
    ("2440", "Wynnum depot amenities building", "Bayside Transport Group Pty Ltd", "Commercial", "Brisbane", 2_210_000, date(2026, 9, 7), date(2027, 6, 25), "active"),
    ("2444", "Southport office tower column strengthening", "Southport Central Investments Pty Ltd", "Remedial", "Gold Coast", 3_760_000, date(2026, 10, 12), date(2027, 8, 27), "active"),
]
SECTORS = ["Remedial", "Body corporate", "Industrial", "Commercial"]

PEOPLE = {
    "estimators": ["Estimator A", "Estimator B", "Estimating lead"],
    "admins": ["Contracts administrator A", "Contracts administrator B"],
    "managers": ["Construction manager", "Commercial manager"],
    "supervisors": ["Site supervisor A", "Site supervisor B", "Site supervisor C"],
}

# Queensland public holidays in the planning window (Brisbane). Working-day
# arithmetic skips these and weekends.
QLD_HOLIDAYS = [
    date(2026, 1, 1), date(2026, 1, 26), date(2026, 4, 3), date(2026, 4, 4), date(2026, 4, 6),
    date(2026, 4, 25), date(2026, 5, 4), date(2026, 8, 12), date(2026, 10, 5), date(2026, 12, 25),
    date(2026, 12, 28), date(2027, 1, 1), date(2027, 1, 26), date(2027, 3, 26), date(2027, 3, 27),
    date(2027, 3, 29), date(2027, 4, 26), date(2027, 5, 3), date(2027, 8, 11), date(2027, 10, 4),
    date(2027, 12, 27), date(2027, 12, 28),
]

# ------------------------------------------------------------- bid summary --
BID_SECTIONS = ["Project details", "Programme", "Direct costs", "Indirect costs", "Margin and risk",
                "Competitors", "Benchmarking"]
# Standard cost codes offered by the grid's autocomplete (code, description, group).
COST_CODES = [
    ("0100", "Preliminaries - site establishment", "indirect"),
    ("0110", "Preliminaries - supervision", "indirect"),
    ("0120", "Preliminaries - scaffold and access", "indirect"),
    ("0130", "Preliminaries - cranage and hoisting", "indirect"),
    ("0140", "Preliminaries - insurances and fees", "indirect"),
    ("0200", "Demolition and strip-out", "direct"),
    ("0300", "Earthworks and piling", "direct"),
    ("0400", "Concrete supply and place", "direct"),
    ("0410", "Reinforcement supply and fix", "direct"),
    ("0420", "Formwork", "direct"),
    ("0430", "Concrete repair and injection", "direct"),
    ("0500", "Structural steel", "direct"),
    ("0600", "Masonry and render", "direct"),
    ("0700", "Waterproofing and membranes", "direct"),
    ("0800", "Roofing and cladding", "direct"),
    ("0900", "Windows, doors and glazing", "direct"),
    ("1000", "Carpentry and joinery", "direct"),
    ("1100", "Painting and protective coatings", "direct"),
    ("1200", "Floor finishes and tiling", "direct"),
    ("1300", "Hydraulic services", "direct"),
    ("1400", "Electrical services", "direct"),
    ("1500", "Mechanical services", "direct"),
    ("1600", "Fire services", "direct"),
    ("1700", "External works", "direct"),
]
BID_HARD_STOPS = [("bid_name", "Bid Name"), ("bid_number", "Bid Number"), ("site_establishment", "Site Establishment"),
                  ("practical_completion", "Practical Completion Date"), ("gross_building_area", "Gross Building Area")]
BID_SOFT_WARNINGS = [("bid_gate", "Bid Gate"), ("submission_date", "Submission Date"),
                     ("contract_execution", "Contract Execution"), ("included_delays", "Included Delays")]
GST_BP = 1000  # 10%
CRM_STAGES = ["qualifying", "tendering", "submitted", "won", "lost"]
COMPETITORS = ["Builder North", "Builder East", "Builder Coastal", "Builder Metro", "Builder Hinterland"]

# ------------------------------------------------------------ trade planner --
# trade, code, [(task, unit, units per worker-hour x1000, default crew)]
TRADES = [
    ("Formwork", "FRM", [("Soffit formwork", "m2", 1400, 4), ("Column formwork", "m2", 900, 3),
                         ("Wall formwork", "m2", 1100, 4), ("Edge boards", "m", 4200, 2), ("Strip and clean", "m2", 3600, 3)]),
    ("Steel fixing", "STF", [("Fix slab reinforcement", "t", 95, 4), ("Fix column cages", "t", 70, 3),
                             ("Fix wall reinforcement", "t", 80, 4), ("Place mesh", "m2", 9000, 2)]),
    ("Concrete placing", "CON", [("Place and finish slab", "m3", 1250, 6), ("Place columns and walls", "m3", 800, 4),
                                 ("Cure and protect", "m2", 22000, 2), ("Saw cut joints", "m", 14000, 2)]),
    ("Concrete repair", "REP", [("Break out defective concrete", "m2", 320, 3), ("Clean and treat reinforcement", "m2", 550, 2),
                                ("Apply repair mortar", "m2", 420, 3), ("Crack injection", "m", 2600, 2)]),
    ("Waterproofing", "WPF", [("Surface preparation", "m2", 5200, 3), ("Apply liquid membrane", "m2", 4300, 3),
                              ("Sheet membrane", "m2", 3100, 3), ("Sealant joints", "m", 7800, 2)]),
    ("Painting and coatings", "PNT", [("Pressure clean", "m2", 16000, 2), ("Patch and prime", "m2", 6200, 3),
                                      ("Apply protective coating", "m2", 5400, 3), ("Line marking", "m", 21000, 2)]),
    ("Carpentry", "CAR", [("Wall framing", "m2", 1900, 3), ("Hang doors", "each", 450, 2),
                          ("Fix-out", "m2", 2400, 3), ("Balustrade install", "m", 1300, 2)]),
    ("Labouring", "LAB", [("Demolition and strip-out", "m2", 2600, 4), ("Material handling", "t", 900, 3),
                          ("Site clean", "m2", 30000, 2), ("Traffic and spotter duties", "hours", 1000, 1)]),
]
# An assumption: loaded cost per hour by classification, cents.
LABOUR_RATES = {"Tradesperson": 9800, "Labourer": 7600, "Leading hand": 11200, "Supervisor": 13500}
ORDINARY_HOURS_X10 = 80          # per day; hours beyond are overtime
OVERTIME_FIRST_HOURS_X10 = 20    # at 1.5x, the remainder at 2.0x
# Advanced-mode production modifiers, percent of the library rate.
MODIFIERS = {
    "access": [("Open access", 100), ("Restricted access", 85), ("Confined or occupied", 70)],
    "complexity": [("Standard programme", 100), ("Staged or out of sequence", 90), ("Night or shutdown works", 80)],
    "crew_mix": [("Experienced crew", 100), ("Mixed crew", 92), ("New crew", 85)],
    "handling": [("Crane or hoist available", 100), ("Manual handling", 88), ("Long carry or stairs only", 76)],
}
NON_PRODUCTION_ROLES = ["Supervisor", "Leading hand", "Safety adviser", "Traffic controller"]

# -------------------------------------------------- material supply register --
MSR_PROJECTS = ["2418", "2427", "2431", "2440"]
MSR_NOT_ENROLLED = ["2444"]  # has work coming; left for the Add Project flow
CONCRETE_SUPPLIERS = [("CPM", "Coastal Premix"), ("RLC", "Ridgeline Concrete")]
REO_SUPPLIER = ("SFR", "SteelFix Reinforcing")
# A supplier whose paperwork has no parser yet: the AI fallback's case.
UNKNOWN_SUPPLIER = ("HVC", "Hinterland Valley Concrete")
# Publishes its dockets and invoices through an API as well as by email.
FEED_SUPPLIER = "Coastal Premix"
CONCRETE_ITEMS = [("N32/20", 27800), ("N40/20", 29600), ("S40/20", 31200)]   # $/m3 in cents, before the July rise
REO_ITEMS = [("Cut and bent bar", 198000), ("Mesh", 176000)]                 # $/t in cents
PRICE_RISE_FROM = date(2026, 7, 1)
PRICE_RISE_BP = 400  # 4%
SURCHARGES = [("Saturday delivery", "per m3", 1800), ("Small load under 3 m3", "per load", 9500),
              ("Waiting time", "per 15 min", 4500)]
RECON_GREEN_BP = 100   # under 1% and every line matched
RECON_AMBER_BP = 500   # 1% to 5%, or an unmatched line; above is red

# ------------------------------------------------------------------- seeded --
SEEDED = {
    # Related-party mirror breaks (amounts in cents, at LEDGER_END).
    "rp_one_sided": {"creditor": "PLT", "debtor": "CON", "month": "2026-09", "amount_cents": 4_620_000,
                     "why": "Plant hire invoiced by the plant company and never booked by the builder."},
    "rp_timing": {"creditor": "PROP", "debtor": "CON", "amount_cents": 3_850_000,
                  "why": "Rent paid by the builder on the last day of October, not yet receipted by the trust."},
    "rp_wrong_party": {"creditor": "HOLD", "booked_to": "PROP", "debtor": "CON", "month": "2026-08", "amount_cents": 2_200_000,
                       "why": "August management fee booked by the builder against the property trust instead of the holding company."},
    # Material Supply Register reconciliation cases.
    "msr_rate_overcharge": {"project": "2418", "why": "Invoice priced at the post-rise rate for dockets delivered before the rise."},
    "msr_unmatched_docket": {"project": "2427", "why": "Invoice line for a docket number that is on no pour in the register."},
    "msr_duplicate_docket": {"project": "2418", "why": "The same docket billed on two invoices."},
    "msr_waiting_time": {"project": "2431", "why": "Waiting time charged that the price list does not carry: a small variance."},
    "msr_fac_overrun": {"project": "2427", "why": "Delivered quantity on a budget line already exceeds its forecast at completion."},
}
