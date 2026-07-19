import config
from paper import net_per_unit

def size_position(equity_inr: float, side: str, entry: float, stop: float, usdt_inr_rate: float):
    if usdt_inr_rate <= 0:
        raise ValueError("Invalid usdt_inr_rate")
    if entry <= 0 or stop <= 0:
        raise ValueError("Invalid entry/stop")

    equity_quote = equity_inr / usdt_inr_rate
    risk_budget_quote = equity_quote * config.RISK_PER_TRADE
    risk_budget_inr = equity_inr * config.RISK_PER_TRADE

    # Includes projected stop exit slippage and both entry/exit fees.
    stop_net_per_unit = net_per_unit(side, entry, stop)
    all_in_loss_per_unit = -stop_net_per_unit
    if all_in_loss_per_unit <= 0:
        raise ValueError("Initial stop does not produce a projected all-in loss")

    raw_qty = risk_budget_quote / all_in_loss_per_unit
    max_notional_quote = equity_quote * config.MAX_LEVERAGE
    qty = min(raw_qty, max_notional_quote / entry)
    qty = max(0.0, qty)

    planned_loss_quote = all_in_loss_per_unit * qty
    planned_loss_inr = planned_loss_quote * usdt_inr_rate
    return qty, risk_budget_quote, risk_budget_inr, planned_loss_inr
