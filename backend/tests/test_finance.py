"""The statements add up, every way they can be added."""

from __future__ import annotations

import pytest

from src.app.services import finance

ENTITIES = ["CON", "PLT", "PROP", "HOLD"]


@pytest.mark.parametrize("entity", ENTITIES + ["GROUP"])
def test_balance_sheet_balances_at_every_month_end(fresh_db, entity):
    for m in finance.month_ends():
        bs = finance.balance_sheet(entity, m.isoformat())
        assert bs["balances"], (entity, m)


def test_group_net_assets_equal_the_sum_of_the_entities(fresh_db):
    group = finance.balance_sheet("GROUP")["totals"]["net_assets"]
    assert round(sum(finance.balance_sheet(e)["totals"]["net_assets"] for e in ENTITIES), 2) == group


def test_group_profit_equals_the_sum_of_the_entities(fresh_db):
    for fy in finance.options()["fin_years"]:
        group = finance.pnl("GROUP", fy)["totals"]["net_profit_ytd"]
        assert round(sum(finance.pnl(e, fy)["totals"]["net_profit_ytd"] for e in ENTITIES), 2) == group


def test_consolidation_removes_intercompany_revenue(fresh_db):
    p = finance.pnl("GROUP")
    names = {line["name"] for s in p["sections"] for line in s["lines"]}
    assert "Related party revenue" not in names
    assert p["elimination"]["revenue"] > 0


def test_monthly_columns_sum_to_the_year(fresh_db):
    p = finance.pnl("CON")
    for s in p["sections"]:
        for line in s["lines"]:
            assert round(sum(line["months"]), 2) == line["ytd"]


def test_unreconciled_intercompany_equals_the_related_party_gap(fresh_db):
    bs = finance.balance_sheet("GROUP")["totals"]["unreconciled_intercompany"]
    rp = finance.related_party()["totals"]["difference"]
    assert round(bs, 2) == round(rp, 2)
