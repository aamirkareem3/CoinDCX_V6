"""V5 research agent. Learns bounded ranking bonuses from resolved shadow observations."""
import json, time
from collections import defaultdict
from v5_memory import feature_buckets

MIN_BUCKET_SAMPLES=30
PRIOR_WINS=5
PRIOR_TOTAL=10
MAX_BONUS=5.0

class ResearchAgent:
    def __init__(self,memory): self.memory=memory

    def run(self):
        rows=self.memory.rows()
        stats=defaultdict(lambda:[0,0])
        reasons=defaultdict(lambda:[0,0,float("0"),float("0")])
        for r in rows:
            win=r["outcome_60m"]=="FAVORABLE"
            m=json.loads(r["metrics_json"])
            for b in feature_buckets(m):
                stats[b][0]+=1; stats[b][1]+=int(win)
            q=reasons[r["status"]]
            q[0]+=1; q[1]+=int(win); q[2]+=float(r["mfe_r_60m"]); q[3]+=float(r["mae_r_60m"])
        promoted=[]
        for b,(n,w) in stats.items():
            if n<MIN_BUCKET_SAMPLES: continue
            posterior=(w+PRIOR_WINS)/(n+PRIOR_TOTAL)
            # 50% posterior is neutral. Bounded to +/-5; this can rank valid setups, never bypass hard safety gates.
            bonus=max(-MAX_BONUS,min(MAX_BONUS,(posterior-.5)*20))
            self.memory.db.execute(
                """INSERT INTO adaptive_weights(bucket,samples,wins,posterior,bonus,updated_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(bucket) DO UPDATE SET
                   samples=excluded.samples,wins=excluded.wins,posterior=excluded.posterior,
                   bonus=excluded.bonus,updated_at=excluded.updated_at""",
                (b,n,w,posterior,bonus,time.time()))
            promoted.append({"bucket":b,"samples":n,"wins":w,"posterior":posterior,"bonus":bonus})
        self.memory.db.commit()
        reason_report=[]
        for reason,(n,w,mfe,mae) in reasons.items():
            reason_report.append({"reason":reason,"samples":n,"favorable_rate":w/n,
                                  "avg_mfe_atr":mfe/n,"avg_mae_atr":mae/n})
        reason_report.sort(key=lambda x:(-x["samples"]))
        report={"resolved":len(rows),"adaptive_buckets":promoted,"rejection_outcomes":reason_report[:15]}
        self.memory.db.execute("INSERT INTO research_runs(ts,resolved_count,report_json) VALUES(?,?,?)",
                               (time.time(),len(rows),json.dumps(report)))
        self.memory.db.commit()
        with open("v5_research_report.json","w",encoding="utf-8") as f: json.dump(report,f,indent=2)
        return report
