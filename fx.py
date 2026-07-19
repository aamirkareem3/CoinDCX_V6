"""
fx.py — USDT -> INR conversion, used by both liquidity.py (24h traded-value
threshold) and risk.py (position sizing), so the two modules can't drift
into two different guesses at the rate.

Tries a live rate off CoinDCX itself first (via the same public candle
endpoint everything else uses); falls back to config.USDT_INR_FALLBACK_RATE
only if none of the candidate symbols resolve. The fallback is never used
silently — callers get an `is_fallback` flag back and are expected to log it.
"""

from __future__ import annotations
import time
import config

_cache = {"rate": None, "is_fallback": True, "fetched_at": 0.0}


def usdt_inr_rate(client) -> tuple[float, bool]:
    """
    Returns (rate, is_fallback). `client` is a CoinDCXPublicClient instance
    (reused so we don't open a second session). Cached for
    config.USDT_INR_CACHE_SECONDS to avoid hammering the candles endpoint
    once per scan/manage cycle.
    """
    now = time.time()
    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < config.USDT_INR_CACHE_SECONDS:
        return _cache["rate"], _cache["is_fallback"]

    for symbol in config.USDT_INR_PAIR_CANDIDATES:
        try:
            df = client.candles(symbol, "15m", limit=2)
            if df is not None and not df.empty:
                rate = float(df["close"].iloc[-1])
                _cache.update(rate=rate, is_fallback=False, fetched_at=now)
                return rate, False
        except Exception:
            continue

    # Nothing resolved — use the static fallback but flag it every time.
    _cache.update(rate=config.USDT_INR_FALLBACK_RATE, is_fallback=True, fetched_at=now)
    return config.USDT_INR_FALLBACK_RATE, True
