from dataclasses import dataclass

import v4_config as c


def slip(price, spread):
    return price * (c.BASE_SLIPPAGE + spread / 100 * c.SLIPPAGE_SPREAD_MULT)


def entry(side, bid, ask, spread):
    return ask + slip(ask, spread) if side == "LONG" else bid - slip(bid, spread)


def exit(side, bid, ask, spread):
    return bid - slip(bid, spread) if side == "LONG" else ask + slip(ask, spread)


def gross_pnl(side, entered, exited, quantity):
    return (exited - entered) * quantity if side == "LONG" else (entered - exited) * quantity


def pnl(side, entered, exited, quantity):
    gross = gross_pnl(side, entered, exited, quantity)
    fees = (entered + exited) * quantity * c.FEE_RATE
    return gross - fees, fees


@dataclass
class Position:
    pair: str
    side: str
    entry: float
    stop: float
    target: float
    qty: float
    risk: float
    opened_at: str
    initial_stop: float = None
    setup_fingerprint: str = ""
    confirmation_id: str = ""
    impulse_id: str = ""
    atr: float = 0.0
    state: str = "OPEN"
    max_r: float = 0.0

    def __post_init__(self):
        if self.initial_stop is None:
            self.initial_stop = self.stop
