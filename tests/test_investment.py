"""Keep/buy/lease arithmetic and saved scenario snapshots."""

from __future__ import annotations

import pytest

from clinic.db import get_db
from clinic.finance import repository as finance_repo
from clinic.finance.investment import (
    InvestmentError,
    OptionInputs,
    ScenarioInputs,
    compare_scenario,
    example_guide_inputs,
    procedures_per_month,
)


def test_guide_example_numbers():
    result = compare_scenario(example_guide_inputs())
    keep = result.options["keep"]
    buy = result.options["buy"]
    lease = result.options["lease"]

    assert keep.procedures_per_month == 10
    assert keep.limiting_factors == ["equipment"]
    assert keep.horizon_net_cash_cents == 1_140_000  # 11_400 €

    assert buy.procedures_per_month == 12  # staff limit, not 40
    assert "staff" in buy.limiting_factors
    assert buy.horizon_net_cash_cents == 808_000  # 8_080 €
    assert buy.incremental_vs_keep_cents == -332_000  # -3_320 €

    assert lease.procedures_per_month == 12
    assert lease.horizon_net_cash_cents == 1_008_000  # 10_080 €
    assert lease.incremental_vs_keep_cents == -132_000  # -1_320 €


def test_staff_bottleneck_after_equipment_increase():
    q, limits = procedures_per_month(
        30,
        OptionInputs(12, 20, 40, 0, 0, 0),
    )
    assert q == 12
    assert limits == ["staff"]


def test_zero_demand():
    q, limits = procedures_per_month(0, OptionInputs(12, 20, 40, 0, 0, 0))
    assert q == 0
    assert "demand" in limits


def test_invalid_months_rejected():
    bad = example_guide_inputs()
    # dataclasses are frozen — rebuild with months=0
    bad = ScenarioInputs(
        name=bad.name,
        procedure_code=bad.procedure_code,
        months=0,
        monthly_demand=bad.monthly_demand,
        expected_receipt_cents=bad.expected_receipt_cents,
        variable_cost_cents=bad.variable_cost_cents,
        keep=bad.keep,
        buy=bad.buy,
        lease=bad.lease,
    )
    with pytest.raises(InvestmentError, match="months"):
        compare_scenario(bad)


def test_save_and_reload_preserves_snapshots(app):
    with app.app_context():
        db = get_db()
        inputs = example_guide_inputs()
        scenario_id = finance_repo.save_investment_scenario(
            db,
            inputs=inputs,
            created_at="2026-10-10T20:00:00",
        )
        loaded = finance_repo.get_investment_scenario(db, scenario_id)
        assert loaded["inputs"]["monthly_demand"] == 30
        assert loaded["outputs"]["options"]["keep"]["horizon_net_cash_cents"] == 1_140_000
        assert loaded["outputs"]["options"]["buy"]["procedures_per_month"] == 12

        # Changing live fee assumptions must not rewrite the saved scenario.
        db.execute(
            "UPDATE fee_assumptions SET expected_fee_cents = 99999 WHERE procedure_code = 'GASTRO'"
        )
        again = finance_repo.get_investment_scenario(db, scenario_id)
        assert again["outputs"]["options"]["keep"]["horizon_net_cash_cents"] == 1_140_000
