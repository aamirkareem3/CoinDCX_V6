"""V5 adaptive memory: local SQLite only, no paid API and no self-modifying code."""
import json, sqlite3, time
from pathlib import Path

DB_FILE = Path("v5_memory.sqlite3")

class AdaptiveMemory:
    def __init__(self, path=DB_FILE):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          fingerprint TEXT UNIQUE, observed_at REAL, signal_time TEXT, pair TEXT, side TEXT,
          status TEXT, ref_price REAL, atr REAL, metrics_json TEXT,
          resolved_60m INTEGER DEFAULT 0, outcome_60m TEXT, mfe_r_60m REAL, mae_r_60m REAL
        );
        CREATE TABLE IF NOT EXISTS research_runs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, resolved_count INTEGER, report_json TEXT
        );
        CREATE TABLE IF NOT EXISTS adaptive_weights(
          bucket TEXT PRIMARY KEY, samples INTEGER, wins INTEGER, posterior REAL, bonus REAL, updated_at REAL
        );
        """)
        self.db.commit()

    def remember(self, pair, result):
        m = result.metrics or {}
        side = result.side
        if side not in ("LONG","SHORT") or not m.get("signal_time") or not m.get("atr5"):
            return False
        fp = f"{pair}|{side}|{m['signal_time']}|{result.status}"
        try:
            self.db.execute(
                """INSERT INTO observations(fingerprint,observed_at,signal_time,pair,side,status,ref_price,atr,metrics_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (fp,time.time(),m["signal_time"],pair,side,result.status,float(m["ref_price"]),
                 float(m["atr5"]),json.dumps(m,default=str)))
            self.db.commit(); return True
        except sqlite3.IntegrityError:
            return False

    def due(self, pair, now=None):
        now = now or time.time()
        return self.db.execute(
            "SELECT * FROM observations WHERE pair=? AND resolved_60m=0 AND observed_at<=?",
            (pair,now-3600)).fetchall()

    def resolve_60m(self, row, candles):
        import pandas as pd
        start = pd.Timestamp(row["signal_time"])
        end = start + pd.Timedelta(minutes=60)
        x = candles[(candles["time"] > start) & (candles["time"] <= end)]
        if len(x) < 6: return False
        ref, atr, side = float(row["ref_price"]), max(float(row["atr"]),1e-12), row["side"]
        if side=="LONG":
            mfe=(float(x.high.max())-ref)/atr; mae=(ref-float(x.low.min()))/atr
        else:
            mfe=(ref-float(x.low.min()))/atr; mae=(float(x.high.max())-ref)/atr
        # Conservative proxy: only call it favorable when 1.8 ATR was available and adverse excursion stayed below 1 ATR.
        outcome="FAVORABLE" if mfe>=1.8 and mae<1.0 else "UNFAVORABLE"
        self.db.execute("UPDATE observations SET resolved_60m=1,outcome_60m=?,mfe_r_60m=?,mae_r_60m=? WHERE id=?",
                        (outcome,mfe,mae,row["id"]))
        self.db.commit(); return True

    def resolved_count(self):
        return int(self.db.execute("SELECT COUNT(*) FROM observations WHERE resolved_60m=1").fetchone()[0])

    def rows(self):
        return self.db.execute("SELECT * FROM observations WHERE resolved_60m=1 ORDER BY observed_at").fetchall()

    def bonus(self, metrics):
        bonuses=[]
        for bucket in feature_buckets(metrics):
            r=self.db.execute("SELECT bonus FROM adaptive_weights WHERE bucket=?",(bucket,)).fetchone()
            if r: bonuses.append(float(r[0]))
        return max(-5.0,min(5.0,sum(bonuses)/len(bonuses))) if bonuses else 0.0

def feature_buckets(m):
    out=[]
    out.append("1h:aligned" if m.get("one_hour_aligned") else "1h:neutral")
    if "adx" in m: out.append("adx:high" if float(m["adx"])>=25 else "adx:mid" if float(m["adx"])>=18 else "adx:low")
    if "efficiency" in m: out.append("eff:high" if float(m["efficiency"])>=.55 else "eff:mid" if float(m["efficiency"])>=.35 else "eff:low")
    if m.get("confirmation"): out.append("confirm:"+str(m["confirmation"]))
    if "fib" in m:
        f=float(m["fib"]); out.append("fib:ideal" if .25<=f<=.75 else "fib:edge")
    if "structure" in m: out.append("structure:"+str(m["structure"]))
    return out
