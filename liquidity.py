from dataclasses import dataclass
import pandas as pd
from indicators import add_indicators
import config

@dataclass
class LiquidityResult:
    passed: bool
    reason: str
    spread_pct: float = float("inf")
    traded_value_usdt: float = 0.0
    traded_value_inr: float = 0.0
    usdt_inr_rate_used: float = 0.0
    rate_is_fallback: bool = True

def check_liquidity(df5: pd.DataFrame, spread_pct: float, usdt_inr_rate: float,
                     rate_is_fallback: bool) -> LiquidityResult:
    if len(df5) < config.MIN_VALID_5M_CANDLES:
        return LiquidityResult(False, "insufficient_candles", spread_pct,
                                usdt_inr_rate_used=usdt_inr_rate, rate_is_fallback=rate_is_fallback)
    recent = df5.tail(288).copy()
    gaps = recent["time"].diff().dt.total_seconds().div(60)
    if gaps.max() > config.MAX_GAP_MINUTES:
        return LiquidityResult(False, "gap_over_15m", spread_pct,
                                usdt_inr_rate_used=usdt_inr_rate, rate_is_fallback=rate_is_fallback)
    if len(recent) < config.MIN_VALID_5M_CANDLES:
        return LiquidityResult(False, "under_285_valid", spread_pct,
                                usdt_inr_rate_used=usdt_inr_rate, rate_is_fallback=rate_is_fallback)

    # CoinDCX candle volume is target-currency (USDT for a *_USDT pair).
    # traded_value_usdt is therefore a USDT notional, NOT rupees — convert
    # before comparing against the INR threshold.
    traded_value_usdt = float((recent["volume"] * recent["close"]).sum())
    traded_value_inr = traded_value_usdt * usdt_inr_rate

    reason_suffix = " [USDT/INR fallback rate used — verify before trusting this pass]" if rate_is_fallback else ""

    if traded_value_inr < config.MIN_TRADED_VALUE_INR_24H:
        return LiquidityResult(False, "low_traded_value" + reason_suffix, spread_pct,
                                traded_value_usdt, traded_value_inr, usdt_inr_rate, rate_is_fallback)
    if spread_pct > config.MAX_SPREAD_PCT:
        return LiquidityResult(False, "spread_too_wide", spread_pct,
                                traded_value_usdt, traded_value_inr, usdt_inr_rate, rate_is_fallback)

    z = add_indicators(recent)
    if ((z["high"] - z["low"]) > config.ABNORMAL_ATR_MULT * z["atr"]).tail(12).any():
        return LiquidityResult(False, "abnormal_candle_last_hour", spread_pct,
                                traded_value_usdt, traded_value_inr, usdt_inr_rate, rate_is_fallback)

    return LiquidityResult(True, "ok" + reason_suffix, spread_pct,
                            traded_value_usdt, traded_value_inr, usdt_inr_rate, rate_is_fallback)
