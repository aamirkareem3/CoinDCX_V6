"""Durable V4 paper-trading state.  No credentials or live-order state exists here."""
import json
import os
import time
from pathlib import Path

import v4_config as c


class State:
    def __init__(self, path=c.STATE_FILE):
        self.path = Path(path)
        self.equity = c.PAPER_CAPITAL_INR
        self.cooldowns = {}
        self.seen = set()  # entered/consumed setup fingerprints
        self.armed_fingerprints = set()
        self.consumed_confirmations = set()
        self.consumed_impulses = set()
        self.armed_setup = None
        self.active_trade = None
        self.load()

    def load(self):
        if not self.path.exists():
            return
        d = json.loads(self.path.read_text(encoding="utf-8"))
        self.equity = float(d.get("equity", self.equity))
        self.cooldowns = d.get("cooldowns", {})
        self.seen = set(d.get("seen", []))
        self.armed_fingerprints = set(d.get("armed_fingerprints", []))
        self.consumed_confirmations = set(d.get("consumed_confirmations", []))
        self.consumed_impulses = set(d.get("consumed_impulses", []))
        self.armed_setup = d.get("armed_setup")
        self.active_trade = d.get("active_trade")

    def save(self):
        payload = {
            "equity": self.equity,
            "cooldowns": self.cooldowns,
            "seen": sorted(self.seen),
            "armed_fingerprints": sorted(self.armed_fingerprints),
            "consumed_confirmations": sorted(self.consumed_confirmations),
            "consumed_impulses": sorted(self.consumed_impulses),
            "armed_setup": self.armed_setup,
            "active_trade": self.active_trade,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, self.path)

    def can_trade(self, pair):
        # Deliberately no UTC-day lock: only one active trade is enforced by the engine.
        return self.active_trade is None and float(self.cooldowns.get(pair, 0)) <= time.time()

    def can_arm(self, setup):
        return (
            self.active_trade is None
            and self.armed_setup is None
            and self.can_trade(setup.pair)
            and setup.fingerprint not in self.seen
            and setup.fingerprint not in self.armed_fingerprints
            and setup.confirmation_id not in self.consumed_confirmations
            and setup.impulse_id not in self.consumed_impulses
        )

    def arm(self, setup_data):
        self.armed_setup = setup_data
        self.armed_fingerprints.add(setup_data["fingerprint"])
        self.save()

    def clear_armed(self):
        self.armed_setup = None
        self.save()

    def set_active_trade(self, position_data):
        self.active_trade = position_data
        self.armed_setup = None
        self.save()

    def update_active_trade(self, position_data):
        self.active_trade = position_data
        self.save()

    def cooldown(self, pair, loss=False):
        self.cooldowns[pair] = time.time() + (c.LOSS_COOLDOWN_SECONDS if loss else c.COOLDOWN_SECONDS)

    def complete(self, pnl_inr, setup_fingerprint, confirmation_id, impulse_id, pair, loss=False):
        self.equity += pnl_inr
        self.seen.add(setup_fingerprint)
        self.consumed_confirmations.add(confirmation_id)
        self.consumed_impulses.add(impulse_id)
        self.cooldown(pair, loss)
        self.active_trade = None
        self.armed_setup = None
        self.save()
