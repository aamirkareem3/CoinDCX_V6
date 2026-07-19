import numpy as np
import pandas as pd
import config

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in x]
    if missing:
        raise ValueError(f"Candles missing numeric columns: {missing}")
    # Defend the indicator boundary as well as the HTTP boundary. This matters for
    # cached/test data and prevents object dtype methods from silently downcasting.
    for column in required:
        x[column] = pd.to_numeric(x[column], errors="coerce").astype("float64")
    if x[required].isna().any().any():
        raise ValueError("Candles contain non-numeric OHLCV values")
    x["ema20"] = x["close"].ewm(span=config.EMA_FAST, adjust=False).mean()
    x["ema50"] = x["close"].ewm(span=config.EMA_SLOW, adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=config.EMA_TREND, adjust=False).mean()

    delta = x["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.where(avg_loss.ne(0), np.nan)
    x["rsi"] = (100.0 - 100.0 / (1.0 + rs)).fillna(100.0).astype("float64")

    prev_close = x["close"].shift(1)
    tr = pd.concat([
        x["high"] - x["low"],
        (x["high"] - prev_close).abs(),
        (x["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1/config.ATR_PERIOD, adjust=False).mean()
    x["vol_sma20"] = x["volume"].rolling(20).mean()
    x["body"] = (x["close"] - x["open"]).abs()
    x["range"] = (x["high"] - x["low"]).clip(lower=1e-12)
    x["upper_wick"] = x["high"] - x[["open", "close"]].max(axis=1)
    x["lower_wick"] = x[["open", "close"]].min(axis=1) - x["low"]
    x["close_location"] = (x["close"] - x["low"]) / x["range"]
    return x

def directional_efficiency(df: pd.DataFrame, n: int) -> float:
    z = df.tail(n)
    if len(z) < n:
        return 0.0
    net = abs(float(z["close"].iloc[-1] - z["close"].iloc[0]))
    path = float(z["close"].diff().abs().sum())
    return net / path if path > 0 else 0.0

def ema_cross_count(df: pd.DataFrame, n: int) -> int:
    z = df.tail(n)
    s = (z["ema20"] > z["ema50"]).astype(int)
    return int(s.diff().abs().fillna(0).sum())

def swing_points(df: pd.DataFrame, left=None, right=None):
    left = config.SWING_LEFT if left is None else left
    right = config.SWING_RIGHT if right is None else right
    highs, lows = [], []
    for i in range(left, len(df)-right):
        h = float(df["high"].iloc[i]); lo = float(df["low"].iloc[i])
        if h >= float(df["high"].iloc[i-left:i+right+1].max()):
            highs.append((i, h))
        if lo <= float(df["low"].iloc[i-left:i+right+1].min()):
            lows.append((i, lo))
    return highs, lows
