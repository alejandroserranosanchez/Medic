"""Keep / buy / lease equipment comparison (Finance domain).

All capacities are procedures-per-month for ONE procedure type.
Money inputs/outputs use integer euro cents.

This is a simplified cash scenario, NOT accounting profit or an investment recommendation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


MODEL_VERSION = "1.0"


class InvestmentError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OptionInputs:
    """Per-option capacities and cash costs (cents / procedures-per-month)."""

    staffed_capacity: int
    room_capacity: int
    equipment_capacity: int  # total resulting equipment capacity for that option
    additional_monthly_staff_cost_cents: int
    monthly_equipment_cash_cost_cents: int  # maintenance and/or lease
    upfront_equipment_cash_cost_cents: int  # purchase/setup once; 0 for keep/lease in the demo


@dataclass(frozen=True)
class ScenarioInputs:
    name: str
    procedure_code: str
    months: int
    monthly_demand: int
    expected_receipt_cents: int
    variable_cost_cents: int
    keep: OptionInputs
    buy: OptionInputs
    lease: OptionInputs


@dataclass(frozen=True)
class OptionResult:
    key: str
    procedures_per_month: int
    limiting_factors: list[str]
    monthly_receipts_cents: int
    monthly_variable_cost_cents: int
    monthly_cash_flow_cents: int
    horizon_net_cash_cents: int
    incremental_vs_keep_cents: int


@dataclass(frozen=True)
class ScenarioResult:
    model_version: str
    options: dict[str, OptionResult]
    assumptions: list[str]


def _require_nonneg_int(name: str, value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise InvestmentError(f"{name} must be an integer") from exc
    if n < 0:
        raise InvestmentError(f"{name} cannot be negative")
    return n


def validate_inputs(inputs: ScenarioInputs) -> None:
    if not inputs.name.strip():
        raise InvestmentError("scenario name is required")
    if not inputs.procedure_code.strip():
        raise InvestmentError("procedure code is required")
    months = _require_nonneg_int("months", inputs.months)
    if months < 1 or months > 60:
        raise InvestmentError("months must be between 1 and 60")
    _require_nonneg_int("monthly_demand", inputs.monthly_demand)
    _require_nonneg_int("expected_receipt_cents", inputs.expected_receipt_cents)
    _require_nonneg_int("variable_cost_cents", inputs.variable_cost_cents)
    for label, opt in (("keep", inputs.keep), ("buy", inputs.buy), ("lease", inputs.lease)):
        _require_nonneg_int(f"{label}.staffed_capacity", opt.staffed_capacity)
        _require_nonneg_int(f"{label}.room_capacity", opt.room_capacity)
        _require_nonneg_int(f"{label}.equipment_capacity", opt.equipment_capacity)
        _require_nonneg_int(
            f"{label}.additional_monthly_staff_cost_cents",
            opt.additional_monthly_staff_cost_cents,
        )
        _require_nonneg_int(
            f"{label}.monthly_equipment_cash_cost_cents",
            opt.monthly_equipment_cash_cost_cents,
        )
        _require_nonneg_int(
            f"{label}.upfront_equipment_cash_cost_cents",
            opt.upfront_equipment_cash_cost_cents,
        )


def procedures_per_month(demand: int, option: OptionInputs) -> tuple[int, list[str]]:
    """q = min(demand, staff, room, equipment). Report every tied limiting factor."""
    caps = {
        "demand": demand,
        "staff": option.staffed_capacity,
        "room": option.room_capacity,
        "equipment": option.equipment_capacity,
    }
    q = min(caps.values())
    limiting = [name for name, value in caps.items() if value == q]
    return q, limiting


def evaluate_option(
    *,
    key: str,
    months: int,
    demand: int,
    expected_receipt_cents: int,
    variable_cost_cents: int,
    option: OptionInputs,
    keep_horizon_cents: int | None,
) -> OptionResult:
    q, limiting = procedures_per_month(demand, option)
    monthly_receipts = q * expected_receipt_cents
    monthly_variable = q * variable_cost_cents
    monthly_flow = (
        monthly_receipts
        - monthly_variable
        - option.additional_monthly_staff_cost_cents
        - option.monthly_equipment_cash_cost_cents
    )
    horizon = months * monthly_flow - option.upfront_equipment_cash_cost_cents
    if keep_horizon_cents is None:
        incremental = 0
    else:
        incremental = horizon - keep_horizon_cents
    return OptionResult(
        key=key,
        procedures_per_month=q,
        limiting_factors=limiting,
        monthly_receipts_cents=monthly_receipts,
        monthly_variable_cost_cents=monthly_variable,
        monthly_cash_flow_cents=monthly_flow,
        horizon_net_cash_cents=horizon,
        incremental_vs_keep_cents=incremental,
    )


def compare_scenario(inputs: ScenarioInputs) -> ScenarioResult:
    validate_inputs(inputs)
    keep = evaluate_option(
        key="keep",
        months=inputs.months,
        demand=inputs.monthly_demand,
        expected_receipt_cents=inputs.expected_receipt_cents,
        variable_cost_cents=inputs.variable_cost_cents,
        option=inputs.keep,
        keep_horizon_cents=None,
    )
    buy = evaluate_option(
        key="buy",
        months=inputs.months,
        demand=inputs.monthly_demand,
        expected_receipt_cents=inputs.expected_receipt_cents,
        variable_cost_cents=inputs.variable_cost_cents,
        option=inputs.buy,
        keep_horizon_cents=keep.horizon_net_cash_cents,
    )
    lease = evaluate_option(
        key="lease",
        months=inputs.months,
        demand=inputs.monthly_demand,
        expected_receipt_cents=inputs.expected_receipt_cents,
        variable_cost_cents=inputs.variable_cost_cents,
        option=inputs.lease,
        keep_horizon_cents=keep.horizon_net_cash_cents,
    )
    return ScenarioResult(
        model_version=MODEL_VERSION,
        options={"keep": keep, "buy": buy, "lease": lease},
        assumptions=[
            "Constant monthly demand over the horizon",
            "Expected receipt collected in the same month as the procedure",
            "Equipment capacity is total resulting capacity, not only the unit bought",
            "Purchase/setup is cash once; no depreciation double-count",
            "Excludes tax, financing, residual value, discounting, and unpaid receipts",
            "Simplified scenario estimate — not accounting profit or advice",
        ],
    )


def inputs_to_dict(inputs: ScenarioInputs) -> dict:
    return asdict(inputs)


def result_to_dict(result: ScenarioResult) -> dict:
    return {
        "model_version": result.model_version,
        "assumptions": list(result.assumptions),
        "options": {key: asdict(value) for key, value in result.options.items()},
    }


def example_guide_inputs() -> ScenarioInputs:
    """Canonical numbers from the review guide §8.3 (fictional)."""
    shared_staff_room = dict(staffed_capacity=12, room_capacity=20, additional_monthly_staff_cost_cents=0)
    return ScenarioInputs(
        name="Guide example GASTRO equipment",
        procedure_code="GASTRO",
        months=12,
        monthly_demand=30,
        expected_receipt_cents=12000,
        variable_cost_cents=2500,
        keep=OptionInputs(
            **shared_staff_room,
            equipment_capacity=10,
            monthly_equipment_cash_cost_cents=0,
            upfront_equipment_cash_cost_cents=0,
        ),
        buy=OptionInputs(
            **shared_staff_room,
            equipment_capacity=40,
            monthly_equipment_cash_cost_cents=5000,  # 50 € maintenance
            upfront_equipment_cash_cost_cents=500000,  # 5_000 €
        ),
        lease=OptionInputs(
            **shared_staff_room,
            equipment_capacity=40,
            monthly_equipment_cash_cost_cents=30000,  # 300 € lease incl. maintenance
            upfront_equipment_cash_cost_cents=0,
        ),
    )
