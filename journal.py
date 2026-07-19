import csv, json
from pathlib import Path
from datetime import datetime, timezone

TRADES = Path("trades.csv")
EVENTS = Path("events.jsonl")

TRADE_FIELDS = [
    "opened_at","closed_at","pair","side","entry","initial_stop","exit_price",
    "qty","score","fees_usdt","fees_inr","pnl_usdt","pnl_inr",
    "usdt_inr_rate","rate_is_fallback","risk_budget_inr","planned_loss_inr","final_r","max_r","mae_r","exit_reason"
]

def event(kind, payload):
    row = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **payload}
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")

def trade(row):
    exists = TRADES.exists()
    with TRADES.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        if not exists: w.writeheader()
        w.writerow({k: row.get(k) for k in TRADE_FIELDS})
