from __future__ import annotations
import requests
import pandas as pd

CANDLES_URL = "https://public.coindcx.com/market_data/candles/"
ORDERBOOK_URL = "https://public.coindcx.com/market_data/orderbook"
ACTIVE_INSTRUMENTS_URL = "https://api.coindcx.com/exchange/v1/derivatives/futures/data/active_instruments"

class CoinDCXPublicClient:
    def __init__(self, timeout: int = 15):
        self.s = requests.Session()
        self.timeout = timeout

    def active_futures_instruments(self, margin_currency: str = "USDT") -> list[str]:
        params = [("margin_currency_short_name[]", margin_currency)]
        r = self.s.get(ACTIVE_INSTRUMENTS_URL, params=params, timeout=self.timeout)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(
                f"ACTIVE_INSTRUMENTS HTTP {r.status_code}: {r.text[:200]}", response=r
            ) from e
        data = r.json()
        if not isinstance(data, list):
            raise ValueError(f"Active instruments response is not a list: {type(data).__name__}")
        return sorted({
            str(pair) for pair in data
            if isinstance(pair, str) and pair.startswith("B-") and pair.endswith("_USDT")
        })

    def candles(self, pair: str, interval: str, limit: int = 300) -> pd.DataFrame:
        r = self.s.get(CANDLES_URL, params={"pair": pair, "interval": interval, "limit": limit},
                       timeout=self.timeout)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"CANDLES HTTP {r.status_code} for {pair} {interval}: {r.text[:200]}", response=r) from e
        data = r.json()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        required = ["open", "high", "low", "volume", "close", "time"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{pair}: candle response missing {missing}")
        # CoinDCX may return numeric fields as strings or mixed JSON values.
        # Normalise them once at the ingress boundary so indicator operations never
        # operate on an object Series (which triggers pandas' downcast warning).
        for c in ["open", "high", "low", "volume", "close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="ms", utc=True)
        return df.dropna(subset=required).sort_values("time").drop_duplicates("time").reset_index(drop=True)

    def orderbook(self, pair: str) -> dict:
        r = self.s.get(ORDERBOOK_URL, params={"pair": pair}, timeout=self.timeout)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"ORDERBOOK HTTP {r.status_code} for {pair}: {r.text[:200]}", response=r) from e
        return r.json()

    def mid_price(self, pair: str) -> float:
        ob = self.orderbook(pair)
        bids = [float(x) for x in ob.get("bids", {}).keys()]
        asks = [float(x) for x in ob.get("asks", {}).keys()]
        if not bids or not asks:
            raise ValueError(f"{pair}: empty order book")
        return (max(bids) + min(asks)) / 2

    def spread_pct(self, pair: str) -> float:
        ob = self.orderbook(pair)
        bids = [float(x) for x in ob.get("bids", {}).keys()]
        asks = [float(x) for x in ob.get("asks", {}).keys()]
        if not bids or not asks:
            return float("inf")
        bid, ask = max(bids), min(asks)
        mid = (bid + ask) / 2
        return ((ask - bid) / mid) * 100 if mid > 0 else float("inf")
