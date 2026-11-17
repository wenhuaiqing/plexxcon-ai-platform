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


@pytest.mark.parametrize("entity", ENTITIES + ["GROUP"])
def test_every_balance_sheet_figure_drills_to_entries_that_add_up_to_it(fresh_db, entity):
    for at in (finance.month_ends()[8], finance.month_ends()[-1]):
        bs = finance.balance_sheet(entity, at.isoformat())
        for s in bs["sections"]:
            for line in s["lines"]:
                if line["account_code"] in ("-", "3100") or not line["balance"]:
                    continue
                e = finance.entries(entity, line["account_code"], "bs", as_at=at.isoformat())
                assert e["closing"] == pytest.approx(line["balance"], abs=0.005), (entity, at, line["name"])
                assert e["opening"] + sum(x["amount"] for x in e["lines"]) == pytest.approx(e["closing"], abs=0.005)


@pytest.mark.parametrize("entity", ENTITIES + ["GROUP"])
def test_every_profit_and_loss_figure_drills_to_entries_that_add_up_to_it(fresh_db, entity):
    pnl = finance.pnl(entity)
    for s in pnl["sections"]:
        for line in s["lines"]:
            e = finance.entries(entity, line["account_code"], "pnl", fin_year=pnl["fin_year"])
            assert e["closing"] == pytest.approx(line["ytd"], abs=0.005), (entity, line["name"])
            for m, v in zip(pnl["periods"], line["months"]):
                assert finance.entries(entity, line["account_code"], "pnl", fin_year=pnl["fin_year"], month=m)["closing"] == pytest.approx(v, abs=0.005)


def test_calculated_lines_do_not_pretend_to_have_entries(client):
    assert client.get("/api/finance/entries?account=3100&statement=bs").status_code == 400
    r = client.get("/api/finance/entries?account=1000&statement=bs&entity=CON").json()
    assert r["count"] > 0 and r["lines"][-1]["balance"] == r["closing"]
