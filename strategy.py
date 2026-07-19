from dataclasses import dataclass
from typing import Optional
import pandas as pd
from indicators import add_indicators
import config

@dataclass
class Signal:
    pair: str
    side: str
    entry: float
    stop: float
    atr: float
    score: int
    reason: str

def recent_swing_low(df, n=10): return float(df["low"].tail(n).min())
def recent_swing_high(df, n=10): return float(df["high"].tail(n).max())

def score_setup(side, d5, d15, spread_pct) -> int:
    c = d5.iloc[-2]
    trend_gap = abs(d15.iloc[-2]["ema20"] - d15.iloc[-2]["ema50"]) / max(d15.iloc[-2]["atr"], 1e-12)
    trend = min(25, int(10 + trend_gap * 10))
    vol_ratio = c["volume"] / max(c["vol_sma20"], 1e-12)
    volume = min(20, int(vol_ratio / 1.5 * 15))
    ema_dist_atr = abs(c["close"] - c["ema20"]) / max(c["atr"], 1e-12)
    pullback = max(0, min(20, int(20 - ema_dist_atr * 10)))
    momentum = 15 if ((side=="LONG" and c["close"]>c["open"]) or (side=="SHORT" and c["close"]<c["open"])) else 0
    execution = max(0, min(10, int(10 * (1 - spread_pct / config.MAX_SPREAD_PCT))))
    rr_quality = 10
    return trend + volume + pullback + momentum + rr_quality + execution

def find_signal(pair: str, raw5: pd.DataFrame, raw15: pd.DataFrame, spread_pct: float) -> Optional[Signal]:
    d5, d15 = add_indicators(raw5), add_indicators(raw15)
    if len(d5) < 60 or len(d15) < 60:
        return None
    # Use completed candles only: -1 may still be forming.
    c, p, t = d5.iloc[-2], d5.iloc[-3], d15.iloc[-2]
    atr = float(c["atr"])
    if atr <= 0 or pd.isna(c["vol_sma20"]):
        return None

    long_ok = (
        t["ema20"] > t["ema50"]
        and abs(c["close"] - c["ema20"]) <= atr
        and 45 <= c["rsi"] <= 60
        and c["close"] > c["open"]
        and c["close"] > p["high"]
        and c["volume"] >= config.VOLUME_MULT_ENTRY * c["vol_sma20"]
    )
    short_ok = (
        t["ema20"] < t["ema50"]
        and abs(c["close"] - c["ema20"]) <= atr
        and 40 <= c["rsi"] <= 55
        and c["close"] < c["open"]
        and c["close"] < p["low"]
        and c["volume"] >= config.VOLUME_MULT_ENTRY * c["vol_sma20"]
    )
    if not long_ok and not short_ok:
        return None

    side = "LONG" if long_ok else "SHORT"
    entry = float(c["close"])
    if side == "LONG":
        stop = max(recent_swing_low(d5.iloc[:-2]), entry - config.INITIAL_ATR_STOP_MULT * atr)
        if stop >= entry: return None
    else:
        stop = min(recent_swing_high(d5.iloc[:-2]), entry + config.INITIAL_ATR_STOP_MULT * atr)
        if stop <= entry: return None

    score = score_setup(side, d5, d15, spread_pct)
    if score < config.MIN_SCORE:
        return None
    return Signal(pair, side, entry, stop, atr, score, "frozen_v1")
