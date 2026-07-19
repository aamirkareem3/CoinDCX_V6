"""V4 precision PAPER engine. Public data only; no order endpoints or credentials."""
import time
from datetime import datetime
from dataclasses import asdict
from datetime import datetime, timezone

import fx
import journal
import v4_config as c
from market_data import CoinDCXPublicClient
from universe import UniverseManager
from v4_paper import Position, entry, exit, pnl
from v4_state import State
from v4_strategy import Setup, evaluate


def status_stamp():
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M:%S %Z")


class BotV4:
    def __init__(self, client=None, state=None, sleep_fn=time.sleep, clock=time.time):
        self.client = client or CoinDCXPublicClient()
        self.state = state or State()
        self.universe = UniverseManager(self.client)
        self.sleep = sleep_fn
        self.clock = clock
        self.invalid = {}
        self.candle_cache = {}
        self.position = self._restore_position(self.state.active_trade)
        self.armed = self._restore_setup(self.state.armed_setup)
        self.next_scan_at = self.clock() if not self.position and not self.armed else None
        self.last_arm_revalidate = 0.0
        self.monitor_failures = 0
        self.last_critical_warning = 0.0

    @staticmethod
    def _restore_position(data):
        return Position(**data) if data else None

    @staticmethod
    def _restore_setup(data):
        return Setup(**data) if data else None

    def candle_bucket(self, interval, now=None):
        seconds = {"5m": 300, "15m": 900, "1h": 3600}[interval]
        return int((self.clock() if now is None else now) // seconds)

    def candles(self, pair, interval, limit, now=None):
        key = (pair, interval, limit)
        bucket = self.candle_bucket(interval, now)
        cached = self.candle_cache.get(key)
        if cached and cached[0] == bucket:
            return cached[1]
        data = self.client.candles(pair, interval, limit)
        self.candle_cache[key] = (bucket, data)
        return data

    def book(self, pair):
        ob = self.client.orderbook(pair)
        bids, asks = ob.get("bids", {}), ob.get("asks", {})
        if not bids or not asks:
            raise ValueError("empty order book")
        bid, ask = max(map(float, bids.keys())), min(map(float, asks.keys()))
        if bid <= 0 or ask <= bid:
            raise ValueError("invalid order book")
        return bid, ask, (ask - bid) / ((ask + bid) / 2) * 100

    def reject(self, pair, ev):
        journal.event("v4_candidate", {"pair": pair, "status": ev.status, **(ev.metrics or {})})

    def evaluate_pair(self, pair):
        d5 = self.candles(pair, "5m", 300)
        d15 = self.candles(pair, "15m", 140)
        d1 = self.candles(pair, "1h", 240)
        _, _, spread = self.book(pair)
        return evaluate(pair, d5, d15, d1, spread)

    def cross_verify(self, setup, allow_current_armed=False):
        """Independent final strategy re-evaluation plus identity/spread checks."""
        current_ok = (
            allow_current_armed and self.state.active_trade is None and
            self.state.armed_setup is not None and
            self.state.armed_setup.get("fingerprint") == setup.fingerprint
        )
        if not current_ok and not self.state.can_arm(setup):
            return False, "state/duplicate lock"
        try:
            ev = self.evaluate_pair(setup.pair)
        except Exception as exc:
            return False, f"cross-verification data error: {exc!r}"
        if not ev.setup or ev.status != "ARMED":
            return False, f"strategy no longer valid: {ev.status}"
        fresh = ev.setup
        if (fresh.side != setup.side or fresh.fingerprint != setup.fingerprint or
                fresh.confirmation_id != setup.confirmation_id or fresh.impulse_id != setup.impulse_id):
            return False, "setup identity changed"
        if fresh.metrics.get("spread", 999) > c.ENTRY_MAX_SPREAD_PCT:
            return False, "spread too wide"
        return True, ""

    def scan(self):
        if self.position or self.armed or self.state.active_trade or self.state.armed_setup:
            return None
        rate, _ = fx.usdt_inr_rate(self.client)
        if self.universe.active_due():
            self.universe.refresh_active()
        if self.universe.whitelist_due():
            self.universe.refresh_whitelist(rate, False)
        best, scanned, rejected = None, 0, {}
        print(f"[{status_stamp()}] STATUS=IDLE_SCAN | scanning {len(self.universe.whitelist)} liquid pairs")
        for pair in self.universe.whitelist:
            if self.invalid.get(pair, 0) > self.clock() or not self.state.can_trade(pair):
                continue
            try:
                ev = self.evaluate_pair(pair)
                scanned += 1
                rejected[ev.status] = rejected.get(ev.status, 0) + 1
                self.reject(pair, ev)
                if ev.setup and self.state.can_arm(ev.setup) and (best is None or ev.setup.score > best.score):
                    best = ev.setup
            except Exception as exc:
                self.invalid[pair] = self.clock() + c.INVALID_SYMBOL_TTL
                journal.event("v4_symbol_invalid", {"pair": pair, "error": repr(exc)})
        if best:
            ok, reason = self.cross_verify(best)
            if ok:
                self.armed = best
                self.state.arm(asdict(best))
                self.last_arm_revalidate = self.clock()
                journal.event("v4_armed", asdict(best))
            else:
                journal.event("v4_arm_rejected", {"pair": best.pair, "reason": reason})
        top = max(rejected, key=rejected.get) if rejected else "none"
        armed_text = f"{self.armed.pair} {self.armed.side}" if self.armed else "none"
        print(f"[{status_stamp()}] STATUS=IDLE_SCAN_COMPLETE | {scanned} evaluated | armed={armed_text} | top rejection={top}")
        return self.armed

    def cancel_armed(self, reason):
        if self.armed:
            journal.event("v4_armed_cancelled", {"pair": self.armed.pair, "fingerprint": self.armed.fingerprint, "reason": reason})
        self.armed = None
        self.state.clear_armed()
        self.next_scan_at = self.clock() + c.IDLE_SCAN_SECONDS

    def armed_cycle(self):
        s = self.armed
        if not s:
            return
        if self.clock() - s.armed_at > c.ARM_TIMEOUT:
            return self.cancel_armed("expired")
        try:
            bid, ask, spread = self.book(s.pair)
            self.monitor_failures = 0
        except Exception as exc:
            return self.monitor_failure("ARMED", exc)
        if spread > c.ENTRY_MAX_SPREAD_PCT:
            return self.cancel_armed("live spread excessive")
        # Hard structural invalidation before trigger.
        live = ask if s.side == "LONG" else bid
        if (s.side == "LONG" and live <= s.stop) or (s.side == "SHORT" and live >= s.stop):
            return self.cancel_armed("structure invalidated before trigger")
        if self.clock() - self.last_arm_revalidate >= c.ARM_REVALIDATE_SECONDS:
            ok, reason = self.cross_verify(s, allow_current_armed=True)
            self.last_arm_revalidate = self.clock()
            if not ok:
                return self.cancel_armed(reason)
        triggered = live >= s.trigger if s.side == "LONG" else live <= s.trigger
        if triggered:
            self.enter(s)

    def enter(self, s):
        if self.position or not self.state.can_trade(s.pair):
            return False
        ok, reason = self.cross_verify(s, allow_current_armed=True)
        if not ok:
            self.cancel_armed(f"pre-entry cross-verification: {reason}")
            return False
        try:
            bid, ask, spread = self.book(s.pair)
        except Exception as exc:
            self.monitor_failure("ARMED", exc)
            return False
        if spread > c.ENTRY_MAX_SPREAD_PCT:
            self.cancel_armed("entry spread changed")
            return False
        px = entry(s.side, bid, ask, spread)
        chase = (px - s.trigger) / s.atr if s.side == "LONG" else (s.trigger - px) / s.atr
        if chase > c.MAX_CHASE_ATR:
            self.cancel_armed("entry chase exceeded")
            return False
        risk_unit = abs(px - s.stop) + 2 * (px * c.FEE_RATE + px * c.BASE_SLIPPAGE)
        quote = self.state.equity / c.PAPER_USDT_INR
        qty = min(quote * c.RISK_PER_TRADE / risk_unit, quote * c.MAX_LEVERAGE / px)
        if qty * px < c.MIN_NOTIONAL:
            self.cancel_armed("minimum notional")
            return False
        self.position = Position(
            s.pair, s.side, px, s.stop, s.target, qty, risk_unit * qty,
            datetime.now(timezone.utc).isoformat(),
            setup_fingerprint=s.fingerprint, confirmation_id=s.confirmation_id,
            impulse_id=s.impulse_id, atr=s.atr,
        )
        self.state.set_active_trade(asdict(self.position))
        self.armed = None
        journal.event("v4_entered", {**asdict(self.position), **s.metrics, "spread": spread})
        print(f"[{status_stamp()}] STATUS=LIVE_MANAGE | {self.position.pair} {self.position.side} | entry={self.position.entry:.8g} | price={self.position.entry:.8g} | SL={self.position.stop:.8g} | TP={self.position.target:.8g}")
        return True

    def manage_quote(self, bid, ask, spread):
        p = self.position
        if not p:
            return None
        mark = bid if p.side == "LONG" else ask
        # Conservative precedence: effective stop first, then TP, then stop updates.
        if (mark <= p.stop if p.side == "LONG" else mark >= p.stop):
            reason = "TRAIL_SL" if p.state == "TRAIL" else ("BE_SL" if p.state == "BE" else "SL")
            gap = mark < p.stop if p.side == "LONG" else mark > p.stop
            return self.close(exit(p.side, bid, ask, spread), reason + ("_GAP" if gap else ""))
        if (mark >= p.target if p.side == "LONG" else mark <= p.target):
            return self.close(exit(p.side, bid, ask, spread), "TP")
        r = ((mark - p.entry) if p.side == "LONG" else (p.entry - mark)) * p.qty / max(p.risk, 1e-9)
        p.max_r = max(p.max_r, r)
        old_stop = p.stop
        reason = None
        if r >= c.BE_R:
            be = p.entry
            new_stop = max(p.stop, be) if p.side == "LONG" else min(p.stop, be)
            if new_stop != p.stop:
                p.stop, p.state, reason = new_stop, "BE", f"break-even activated at {r:.2f}R"
        if r >= c.TRAIL_R:
            candidate = mark - c.TRAIL_ATR * p.atr if p.side == "LONG" else mark + c.TRAIL_ATR * p.atr
            new_stop = max(p.stop, candidate) if p.side == "LONG" else min(p.stop, candidate)
            if (p.side == "LONG" and new_stop > p.stop) or (p.side == "SHORT" and new_stop < p.stop):
                p.stop, p.state, reason = new_stop, "TRAIL", f"{c.TRAIL_ATR:.2f} ATR trail at {r:.2f}R"
        if p.stop != old_stop:
            journal.event("v4_trail_move", {"pair": p.pair, "side": p.side, "entry": p.entry, "current_price": mark, "old_stop": old_stop, "new_stop": p.stop, "reason": reason})
            self.state.update_active_trade(asdict(p))
        elif r > p.max_r:
            self.state.update_active_trade(asdict(p))
        return None

    def manage(self):
        if not self.position:
            return
        try:
            bid, ask, spread = self.book(self.position.pair)
            self.monitor_failures = 0
            self.manage_quote(bid, ask, spread)
        except Exception as exc:
            self.monitor_failure("LIVE", exc)

    def monitor_failure(self, mode, exc):
        self.monitor_failures += 1
        journal.event("v4_monitor_data_failure", {"mode": mode, "failures": self.monitor_failures, "error": repr(exc)})
        if self.monitor_failures >= c.MONITOR_CRITICAL_FAILURES and self.clock() - self.last_critical_warning >= 60:
            print(f"[{status_stamp()}] STATUS={mode}_WARNING | consecutive data failures={self.monitor_failures} | state preserved")
            self.last_critical_warning = self.clock()

    def close(self, fill, reason):
        p = self.position
        value, fees = pnl(p.side, p.entry, fill, p.qty)
        inr = value * c.PAPER_USDT_INR
        final_r = value / max(p.risk, 1e-9)
        self.state.complete(inr, p.setup_fingerprint, p.confirmation_id, p.impulse_id, p.pair, inr < 0)
        journal.trade({
            "opened_at": p.opened_at, "closed_at": datetime.now(timezone.utc).isoformat(),
            "pair": p.pair, "side": p.side, "entry": p.entry, "initial_stop": p.initial_stop,
            "exit_price": fill, "qty": p.qty, "fees_usdt": fees, "fees_inr": fees * c.PAPER_USDT_INR,
            "pnl_usdt": value, "pnl_inr": inr, "final_r": final_r, "max_r": p.max_r,
            "exit_reason": reason,
        })
        journal.event("v4_exit", {"reason": reason, "pnl_inr": inr, "equity": self.state.equity})
        print(f"[{status_stamp()}] STATUS=EXIT | {p.pair} {p.side} | price={fill:.8g} | reason={reason} | P&L INR={inr:.2f} | R={final_r:.2f}")
        self.position = None
        self.armed = None
        self.next_scan_at = self.clock() + c.IDLE_SCAN_SECONDS
        return reason

    def cycle(self):
        if self.position:
            self.manage()
            return "LIVE_MANAGE"
        if self.armed:
            self.armed_cycle()
            return "ARMED"
        if self.clock() >= (self.next_scan_at or 0):
            self.scan()
            self.next_scan_at = self.clock() + c.IDLE_SCAN_SECONDS
        return "IDLE_SCAN"

    def run(self):
        print(f"[{status_stamp()}] CoinDCX V4.1 PRECISION CONFLUENCE | PAPER ONLY | IDLE_SCAN -> ARMED -> LIVE_MANAGE -> EXIT")
        if self.position:
            print(f"[{status_stamp()}] STATUS=LIVE_RECOVERED | {self.position.pair} {self.position.side} | entry={self.position.entry:.8g} | price=awaiting fresh quote | scanning disabled")
        elif self.armed:
            print(f"[{status_stamp()}] STATUS=ARMED_RECOVERED | {self.armed.pair} {self.armed.side} | trigger={self.armed.trigger:.8g} | price=awaiting fresh quote | validating before trigger")
        while True:
            try:
                mode = self.cycle()
                self.sleep(c.MONITOR_SECONDS if mode in ("ARMED", "LIVE_MANAGE") else c.IDLE_LOOP_SLEEP_SECONDS)
            except KeyboardInterrupt:
                break
            except Exception as exc:
                journal.event("v4_engine_error", {"error": repr(exc)})
                self.sleep(5)


if __name__ == "__main__":
    BotV4().run()
