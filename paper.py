from dataclasses import dataclass
from datetime import datetime, timezone
import config

def entry_fill(signal):
    slip = signal.entry * config.ASSUMED_SLIPPAGE_RATE_PER_SIDE
    return signal.entry + slip if signal.side == "LONG" else signal.entry - slip

def exit_fill(side, trigger_price):
    slip = trigger_price * config.ASSUMED_SLIPPAGE_RATE_PER_SIDE
    return trigger_price - slip if side == "LONG" else trigger_price + slip

def net_per_unit(side, entry, trigger_price):
    """Projected net quote-currency P&L per base unit after exit slippage + both-side fees."""
    fill = exit_fill(side, trigger_price)
    if side == "LONG":
        gross = fill - entry
    else:
        gross = entry - fill
    fees = (entry + fill) * config.ASSUMED_FEE_RATE_PER_SIDE
    return gross - fees

def trigger_for_net_per_unit(side, entry, target_net_per_unit):
    """Exact inverse of net_per_unit under the frozen linear fee/slippage model."""
    f = config.ASSUMED_FEE_RATE_PER_SIDE
    s = config.ASSUMED_SLIPPAGE_RATE_PER_SIDE
    if side == "LONG":
        return (target_net_per_unit + entry*(1+f)) / ((1-s)*(1-f))
    return (entry*(1-f) - target_net_per_unit) / ((1+s)*(1+f))

@dataclass
class Position:
    pair: str
    side: str
    entry: float
    stop: float
    initial_stop: float
    qty: float
    score: int
    risk_budget_quote: float
    risk_budget_inr: float
    state: str = "ENTERED"
    max_price: float = 0.0
    min_price: float = float("inf")
    max_r: float = 0.0
    mae_r: float = 0.0
    opened_at: str = ""

    def __post_init__(self):
        if not self.opened_at:
            self.opened_at = datetime.now(timezone.utc).isoformat()
        self.max_price = self.entry
        self.min_price = self.entry

    def projected_net_quote(self, trigger_price):
        return net_per_unit(self.side, self.entry, trigger_price) * self.qty

    def current_r(self, price):
        if self.risk_budget_quote <= 0:
            return 0.0
        return self.projected_net_quote(price) / self.risk_budget_quote

    def trigger_for_net_r(self, target_r):
        target_total = target_r * self.risk_budget_quote
        return trigger_for_net_per_unit(self.side, self.entry, target_total / self.qty)

    def update_extremes(self, price):
        self.max_price = max(self.max_price, price)
        self.min_price = min(self.min_price, price)
        r = self.current_r(price)
        self.max_r = max(self.max_r, r)
        self.mae_r = min(self.mae_r, r)

def net_pnl(pos, exit_price):
    gross = (exit_price-pos.entry)*pos.qty if pos.side=="LONG" else (pos.entry-exit_price)*pos.qty
    fees = (pos.entry*pos.qty + exit_price*pos.qty) * config.ASSUMED_FEE_RATE_PER_SIDE
    return gross - fees, fees
