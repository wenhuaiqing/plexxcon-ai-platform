"""The arithmetic, on cases worked by hand."""

from __future__ import annotations

from datetime import date

from src.app.calc import bid, trade
from src.app.calc.money import rhu, to_cents, to_scaled


def test_money_parsing_rounds_half_up():
    assert to_cents("1,234.565") == 123457
    assert to_cents("$10") == 1000
    assert to_scaled("7.6", 10) == 76
    assert rhu(5, 2) == 3 and rhu(-5, 2) == -3


def test_bid_totals_by_hand():
    data = bid.blank()
    data["direct"] = [{"amount": "100000"}, {"amount": "50000"}]
    data["indirect"] = [{"amount": "20000"}]
    data["margin"] = {"contingency_pct": "2.5", "margin_pct": "8", "escalation": "5000"}
    data["project"]["gross_building_area"] = "1000"
    t = bid.totals(data)
    assert t["contingency_cents"] == 425_000          # 2.5% of $170,000
    assert t["grand_total_cents"] == 17_925_000       # 170,000 + 4,250 + 5,000
    assert t["final_ex_cents"] == 19_359_000          # plus 8%
    assert t["final_inc_cents"] == 21_294_900         # plus GST
    assert t["rate_per_m2_cents"] == 19_359           # $193.59 a square metre


def test_bid_validation_two_tiers():
    v = bid.validate(bid.blank())
    assert len(v["hard"]) == 5 and len(v["soft"]) == 4


def test_working_days_skip_weekends_and_holidays():
    hol = {date(2026, 12, 25), date(2026, 12, 28)}
    # Thu 24/12 is day 1; Fri 25 and Mon 28 are holidays; the weekend is off.
    assert trade.add_working_days(date(2026, 12, 24), 3, False, hol) == date(2026, 12, 30)
    assert trade.add_working_days(date(2026, 12, 26), 1, True, hol) == date(2026, 12, 26)


def test_overtime_split_and_finish():
    rates = {"X": {"rate_code": "X", "task": "Task", "unit": "m2", "rate_x1000": 1000}}
    scope = {"project": {"project_id": "1", "target_start": "2027-02-01", "target_finish": "2027-02-28", "hours_per_day": "10",
                         "mobilisations": [{"id": "M1", "name": "M1", "start": "2027-02-01"}]},
             "trades": [{"trade": "Formwork", "mobilisation_id": "M1", "crew_size": 2, "classification": "Tradesperson",
                         "tasks": [{"rate_code": "X", "quantity": "100", "location": "L"}]}],
             "non_production": {"waived": True}}
    r = trade.calculate(scope, rates, labour_rates={"Tradesperson": 10000}, holidays=[])
    t = r["trades"][0]
    assert t["hours_x100"] == 10000 and t["work_days"] == 5          # 100 h, crew of 2 at 10 h a day
    assert t["ordinary_hours_x100"] == 8000 and t["overtime_hours_x100"] == 2000
    assert t["labour_cents"] == 8000 * 100 + 2000 * 150              # 80 h at $100, 20 h at $150
    assert t["finish_date"] == "2027-02-05" and t["on_time"]


def test_modifiers_slow_the_rate():
    assert trade.modifier_x10000({"access": 85, "complexity": 90}) == 7650
    assert trade.task_hours_x100(10000, 1000, 5000) == 20000


def test_location_codes():
    codes = trade.location_codes("2418", [{"zone": "a", "basements": 1, "grounds": 1, "levels": 2}])
    assert [c["code"] for c in codes] == ["2418-A-B1", "2418-A-GF", "2418-A-L01", "2418-A-L02"]
