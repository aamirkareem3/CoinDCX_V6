from dataclasses import dataclass
from typing import Optional
import time
import pandas as pd
import config
from indicators import add_indicators, directional_efficiency, ema_cross_count, swing_points

@dataclass
class ArmedSetup:
    pair: str
    side: str
    score: int
    trigger: float
    stop: float
    atr: float
    target: float
    rr: float
    fib_pct: float
    confirm_type: str
    structure: str
    impulse_low: float
    impulse_high: float
    armed_at: float
    reason: str

@dataclass
class Evaluation:
    pair: str
    side: str
    score: int
    status: str
    setup: Optional[ArmedSetup] = None

def _trend(d15, d1h):
    a = d15.iloc[-2]
    h = d1h.iloc[-2]
    atr = max(float(a["atr"]), 1e-12)
    gap = abs(float(a["ema20"] - a["ema50"])) / atr
    slope = abs(float(d15["ema20"].iloc[-2] - d15["ema20"].iloc[-5])) / (3*atr)
    long = a["ema20"] > a["ema50"] and h["ema20"] > h["ema50"] and h["close"] > h["ema200"]
    short = a["ema20"] < a["ema50"] and h["ema20"] < h["ema50"] and h["close"] < h["ema200"]
    if not long and not short:
        return None, gap, slope
    return ("LONG" if long else "SHORT"), gap, slope

def _structure(d15, side):
    highs, lows = swing_points(d15.iloc[:-1])
    if len(highs) < 2 or len(lows) < 2:
        return False, "insufficient swings"
    h1, h2 = highs[-2][1], highs[-1][1]
    l1, l2 = lows[-2][1], lows[-1][1]
    if side == "LONG":
        ok = h2 > h1 and l2 > l1
        return ok, "HH-HL" if ok else "not HH-HL"
    ok = h2 < h1 and l2 < l1
    return ok, "LH-LL" if ok else "not LH-LL"

def _consolidating(d5):
    z = d5.iloc[:-1].tail(config.CONSOLIDATION_LOOKBACK)
    atr = max(float(z["atr"].iloc[-1]), 1e-12)
    range_atr = float(z["high"].max() - z["low"].min()) / atr
    crosses = ema_cross_count(z, len(z))
    eff = directional_efficiency(z, len(z))
    bad = (range_atr <= config.MAX_CONSOLIDATION_RANGE_ATR
           and crosses >= config.MAX_EMA_CROSSES_IN_LOOKBACK
           and eff < config.MIN_DIRECTIONAL_EFFICIENCY)
    return bad, range_atr, crosses, eff

def _impulse_and_fib(d5, side):
    z = d5.iloc[:-2].tail(config.IMPULSE_LOOKBACK)
    if len(z) < 15:
        return None
    atr = max(float(d5["atr"].iloc[-2]), 1e-12)
    if side == "LONG":
        low_i = int(z["low"].values.argmin())
        after = z.iloc[low_i:]
        if len(after) < 3: return None
        high_rel = int(after["high"].values.argmax())
        high_i = low_i + high_rel
        if high_i <= low_i: return None
        lo, hi = float(z["low"].iloc[low_i]), float(z["high"].iloc[high_i])
        impulse = hi-lo
        if impulse < config.MIN_IMPULSE_ATR*atr: return None
        price = float(d5["close"].iloc[-2])
        retr = (hi-price)/impulse
        return lo, hi, retr
    high_i = int(z["high"].values.argmax())
    after = z.iloc[high_i:]
    if len(after) < 3: return None
    low_rel = int(after["low"].values.argmin())
    low_i = high_i + low_rel
    if low_i <= high_i: return None
    hi, lo = float(z["high"].iloc[high_i]), float(z["low"].iloc[low_i])
    impulse = hi-lo
    if impulse < config.MIN_IMPULSE_ATR*atr: return None
    price = float(d5["close"].iloc[-2])
    retr = (price-lo)/impulse
    return lo, hi, retr

def _confirm(d5, side):
    c = d5.iloc[-2]
    prior = d5.iloc[-2-config.SWEEP_LOOKBACK:-2]
    atr = max(float(c["atr"]), 1e-12)
    body_atr = float(c["body"])/atr
    range_atr = float(c["range"])/atr
    vol_ratio = float(c["volume"])/max(float(c["vol_sma20"]), 1e-12)
    if body_atr < config.MIN_CONFIRM_BODY_ATR or range_atr < config.MIN_CONFIRM_RANGE_ATR:
        return False, "weak confirmation candle", ""
    if vol_ratio < config.MIN_CONFIRM_VOLUME_RATIO:
        return False, f"confirm volume {vol_ratio:.2f}x", ""
    body = max(float(c["body"]), 1e-12)
    if side == "LONG":
        sweep = float(c["low"]) < float(prior["low"].min()) and float(c["close"]) > float(prior["low"].min())
        rejection = float(c["lower_wick"])/body >= config.MIN_REJECTION_WICK_BODY
        engulf = c["close"] > c["open"] and c["close"] >= d5["open"].iloc[-3] and c["open"] <= d5["close"].iloc[-3]
        close_ok = float(c["close_location"]) >= config.MIN_CONFIRM_CLOSE_LOCATION
        ok = c["close"] > c["open"] and close_ok and (sweep or rejection or engulf)
        typ = "LIQUIDITY_SWEEP" if sweep else ("BULLISH_ENGULF" if engulf else "BULLISH_REJECTION")
    else:
        sweep = float(c["high"]) > float(prior["high"].max()) and float(c["close"]) < float(prior["high"].max())
        rejection = float(c["upper_wick"])/body >= config.MIN_REJECTION_WICK_BODY
        engulf = c["close"] < c["open"] and c["close"] <= d5["open"].iloc[-3] and c["open"] >= d5["close"].iloc[-3]
        close_ok = float(c["close_location"]) <= 1-config.MIN_CONFIRM_CLOSE_LOCATION
        ok = c["close"] < c["open"] and close_ok and (sweep or rejection or engulf)
        typ = "LIQUIDITY_SWEEP" if sweep else ("BEARISH_ENGULF" if engulf else "BEARISH_REJECTION")
    return ok, ("ok" if ok else "no rejection/sweep/engulf confirmation"), typ

def _target_and_rr(d5, side, trigger, stop):
    risk = abs(trigger-stop)
    if risk <= 0: return None, 0.0
    z = d5.iloc[:-2].tail(config.STRUCTURE_TARGET_LOOKBACK)
    if side == "LONG":
        levels = [float(x) for x in z["high"] if float(x) > trigger]
        target = min(levels) if levels else trigger + 2*risk
        rr = (target-trigger)/risk
    else:
        levels = [float(x) for x in z["low"] if float(x) < trigger]
        target = max(levels) if levels else trigger - 2*risk
        rr = (trigger-target)/risk
    return target, rr

def evaluate_precision(pair: str, raw5: pd.DataFrame, raw15: pd.DataFrame,
                       raw1h: pd.DataFrame, spread_pct: float) -> Evaluation:
    d5, d15, d1h = add_indicators(raw5), add_indicators(raw15), add_indicators(raw1h)
    if len(d5) < 80 or len(d15) < 80 or len(d1h) < 80:
        return Evaluation(pair, "-", 0, "insufficient candles")

    side, gap, slope = _trend(d15, d1h)
    if side is None:
        return Evaluation(pair, "-", 0, "1H/15M trend conflict")
    if gap < config.MIN_TREND_GAP_ATR:
        return Evaluation(pair, side, 20, f"weak EMA separation {gap:.2f} ATR")
    if slope < config.MIN_EMA_SLOPE_ATR:
        return Evaluation(pair, side, 25, f"flat EMA slope {slope:.2f}")

    struct_ok, structure = _structure(d15, side)
    if not struct_ok:
        return Evaluation(pair, side, 35, structure)

    bad_chop, range_atr, crosses, eff = _consolidating(d5)
    if bad_chop:
        return Evaluation(pair, side, 40, f"CONSOLIDATION range {range_atr:.2f}ATR crosses {crosses} eff {eff:.2f}")

    imp = _impulse_and_fib(d5, side)
    if imp is None:
        return Evaluation(pair, side, 48, "no clean impulse")
    lo, hi, retr = imp
    atr = float(d5["atr"].iloc[-2])
    tol = config.FIB_TOLERANCE_ATR / max((hi-lo)/max(atr,1e-12), 1e-12)
    if not config.FIB_MIN-tol <= retr <= config.FIB_MAX+tol:
        return Evaluation(pair, side, 58, f"pullback {retr*100:.1f}% outside Fib zone")

    c = d5.iloc[-2]
    rsi = float(c["rsi"])
    if side == "LONG" and not config.LONG_RSI_MIN <= rsi <= config.LONG_RSI_MAX:
        return Evaluation(pair, side, 62, f"RSI context {rsi:.1f}")
    if side == "SHORT" and not config.SHORT_RSI_MIN <= rsi <= config.SHORT_RSI_MAX:
        return Evaluation(pair, side, 62, f"RSI context {rsi:.1f}")

    ext = abs(float(c["close"]-c["ema20"])) / max(atr,1e-12)
    if ext > config.MAX_EMA_EXTENSION_ATR:
        return Evaluation(pair, side, 64, f"extended {ext:.2f} ATR from EMA20")

    confirm_ok, confirm_reason, confirm_type = _confirm(d5, side)
    if not confirm_ok:
        return Evaluation(pair, side, 68, confirm_reason)

    if side == "LONG":
        trigger = float(c["high"]) + config.TRIGGER_BUFFER_ATR*atr
        stop = min(float(c["low"]), float(d5.iloc[-8:-2]["low"].min()))
    else:
        trigger = float(c["low"]) - config.TRIGGER_BUFFER_ATR*atr
        stop = max(float(c["high"]), float(d5.iloc[-8:-2]["high"].max()))

    stop_atr = abs(trigger-stop)/max(atr,1e-12)
    if stop_atr < config.MIN_STOP_ATR or stop_atr > config.MAX_STOP_ATR:
        return Evaluation(pair, side, 70, f"stop distance {stop_atr:.2f} ATR")

    target, rr = _target_and_rr(d5, side, trigger, stop)
    if rr < config.MIN_RR_TO_STRUCTURE:
        return Evaluation(pair, side, 72, f"structure R:R {rr:.2f}")

    vol_ratio = float(c["volume"])/max(float(c["vol_sma20"]),1e-12)
    score = 50
    score += min(10, int(gap*8))
    score += min(8, int(slope*20))
    score += 8
    score += min(8, int(max(0, vol_ratio-0.8)*8)+3)
    score += 8 if confirm_type == "LIQUIDITY_SWEEP" else 5
    score += min(8, int((rr-config.MIN_RR_TO_STRUCTURE)*4)+4)
    score = min(100, score)

    if score < config.MIN_PRECISION_SCORE:
        return Evaluation(pair, side, score, f"precision score {score} below {config.MIN_PRECISION_SCORE}")

    setup = ArmedSetup(
        pair=pair, side=side, score=score, trigger=trigger, stop=stop, atr=atr,
        target=target, rr=rr, fib_pct=retr*100, confirm_type=confirm_type,
        structure=structure, impulse_low=lo, impulse_high=hi, armed_at=time.time(),
        reason="V3_PRECISION_CONFIRMATION_BREAK"
    )
    return Evaluation(pair, side, score, "ARMED - waiting confirmation high/low break", setup)
