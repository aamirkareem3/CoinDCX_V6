"""Cheap 5m candidate prefilter. Never authorizes entry; full strategy remains mandatory."""
from indicators import add_indicators
from v4_strategy import closed
import v4_config as c

def prefilter(pair, d5):
    if d5 is None or len(d5) < 80:
        return None
    x = add_indicators(closed(d5))
    if len(x) < 30:
        return None
    q=x.iloc[-1]
    atr=max(float(q.atr),1e-12)
    move=abs(float(q.close)-float(x.close.iloc[-4]))/atr
    slope=(float(q.ema20)-float(x.ema20.iloc[-4]))/(3*atr)
    separation=abs(float(q.ema20)-float(q.ema50))/atr
    # Broad prefilter: deliberately looser than the full V5 gates.
    if move < c.FAST_MIN_MOVE_ATR and abs(slope) < .015:
        return None
    score=move + 2*abs(slope) + .25*separation
    return {"pair":pair,"fast_score":float(score),"ref_price":float(q.close),"signal_time":str(q.time)}
