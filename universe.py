from __future__ import annotations
import time
import config
import journal
from liquidity import check_liquidity

class UniverseManager:
    def __init__(self, client):
        self.client = client
        self.active, self.whitelist = [], []
        self.active_refreshed_at = self.whitelist_refreshed_at = 0.0

    def active_due(self):
        return not self.active or time.time()-self.active_refreshed_at >= config.ACTIVE_INSTRUMENTS_REFRESH_SECONDS

    def whitelist_due(self):
        return not self.whitelist or time.time()-self.whitelist_refreshed_at >= config.LIQUIDITY_WHITELIST_REFRESH_SECONDS

    def refresh_active(self):
        items = self.client.active_futures_instruments(config.FUTURES_MARGIN_CURRENCY)
        if not items: raise RuntimeError("Zero compatible active USDT futures returned")
        self.active, self.active_refreshed_at = items, time.time()
        journal.event("active_universe_refreshed", {"count": len(items)})

    def refresh_whitelist(self, rate, fallback):
        if self.active_due(): self.refresh_active()
        passed = []
        print(f"Building liquidity whitelist from {len(self.active)} active USDT futures...")
        for i, pair in enumerate(self.active, 1):
            try:
                d5 = self.client.candles(pair, "5m", config.CANDLE_LIMIT_5M)
                stage1 = check_liquidity(d5, 0.0, rate, fallback)
                if stage1.passed:
                    spread = self.client.spread_pct(pair)
                    final = check_liquidity(d5, spread, rate, fallback)
                    if final.passed: passed.append(pair)
            except Exception as e:
                journal.event("universe_pair_error", {"pair":pair, "error":repr(e)})
            if i % 50 == 0 or i == len(self.active):
                print(f"Universe progress: {i}/{len(self.active)} | liquid so far: {len(passed)}")
            time.sleep(config.UNIVERSE_REQUEST_PAUSE_SECONDS)
        if passed:
            self.whitelist, self.whitelist_refreshed_at = sorted(passed), time.time()
            journal.event("liquidity_whitelist_refreshed",
                          {"active_count":len(self.active),"liquid_count":len(passed),"fx_fallback":fallback})
        elif not self.whitelist:
            raise RuntimeError("Initial liquidity whitelist empty; inspect events.jsonl")
        else:
            journal.event("whitelist_refresh_kept_previous", {"count":len(self.whitelist)})
