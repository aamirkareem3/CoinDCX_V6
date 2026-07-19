from dataclasses import dataclass
import hashlib,time
import pandas as pd
from indicators import add_indicators,directional_efficiency,ema_cross_count,swing_points
import v4_config as c

@dataclass
class Setup:
 pair:str; side:str; trigger:float; stop:float; target:float; atr:float; score:int; confirmation_id:str; fingerprint:str; impulse_id:str; impulse_age:int; fib:float; confirmation:str; quality:int; metrics:dict; armed_at:float=0
@dataclass
class Eval: side:str='-'; status:str=''; setup:object=None; metrics:dict=None

def closed(df): return df.iloc[:-1].copy()
def valid_candles(df,minutes,now=None):
 if len(df)<80:return False,'insufficient candles'
 t=pd.to_datetime(df['time'],utc=True); d=t.diff().dropna().dt.total_seconds()/60
 if not d.between(minutes*.9,minutes*1.1).all(): return False,'interval misalignment'
 if now is not None and (pd.Timestamp(now,tz='UTC')-t.iloc[-1]).total_seconds()>minutes*120:return False,'stale candles'
 return True,''

def adx(x,n=14):
 up=x.high.diff(); dn=-x.low.diff()
 plus=up.where((up>dn)&(up>0),0).rolling(n).mean()
 minus=dn.where((dn>up)&(dn>0),0).rolling(n).mean()
 dx=100*(plus-minus).abs()/(plus+minus).replace(0,1)
 return float(dx.rolling(n).mean().iloc[-1])

def structure(x,side):
 hs,ls=swing_points(x)
 if len(hs)<2 or len(ls)<2:return False,'insufficient confirmed swings',[]
 h1,h2=hs[-2][1],hs[-1][1]; l1,l2=ls[-2][1],ls[-1][1]
 ok=(h2>h1 and l2>l1) if side=='LONG' else (h2<h1 and l2<l1)
 levels=[v for _,v in (hs if side=='LONG' else ls)]
 return ok,('HH-HL' if side=='LONG' else 'LH-LL') if ok else 'mixed structure',levels

def impulse(x,side):
 a=float(x.atr.iloc[-1]); best=None
 for i in range(max(2,len(x)-36),len(x)-3):
  for j in range(i+1,min(len(x),i+10)):
   move=float(x.high.iloc[j]-x.low.iloc[i]) if side=='LONG' else float(x.high.iloc[i]-x.low.iloc[j])
   directional=(x.close.iloc[j]>x.open.iloc[j]) if side=='LONG' else (x.close.iloc[j]<x.open.iloc[j])
   if move>=c.MIN_IMPULSE_ATR*a and directional: best=(i,j,move)
 if not best:return None
 i,j,move=best; age=len(x)-1-j
 if age>c.MAX_IMPULSE_AGE:return None
 lo=float(x.low.iloc[i]); hi=float(x.high.iloc[j]) if side=='LONG' else float(x.high.iloc[i])
 end=float(x.high.iloc[j]) if side=='LONG' else float(x.low.iloc[j])
 p=float(x.close.iloc[-1]); fib=(end-p)/move if side=='LONG' else (p-end)/move
 pull=x.iloc[j+1:]
 intact=len(pull)>=1 and (float(pull.low.min())>lo if side=='LONG' else float(pull.high.max())<hi)
 return i,j,age,lo,hi,fib,intact

def confirmation(x,side,levels):
 q=x.iloc[-1]; p=x.iloc[-2]; atr=max(float(q.atr),1e-9)
 body=float(q.body)/atr; loc=float(q.close_location); vol=float(q.volume)/max(float(q.vol_sma20),1)
 bull=side=='LONG'
 directional=(q.close>q.open) if bull else (q.close<q.open)
 strong=directional and body>=.35 and (loc>=.62 if bull else loc<=.38)
 sweep=False; breakout=False
 if levels:
  recent=levels[-3:]
  sweep=(q.low<max(recent) and q.close>max(recent)) if bull else (q.high>min(recent) and q.close<min(recent))
  breakout=(q.close>max(levels[-2:])) if bull else (q.close<min(levels[-2:]))
 engulf=(q.close>p.open and q.open<=p.close) if bull else (q.close<p.open and q.open>=p.close)
 if sweep and directional:return 'LIQUIDITY_SWEEP',92
 if engulf and strong:return 'ENGULFING_DISPLACEMENT',88
 if breakout and strong:return 'BREAKOUT_CONTINUATION',85
 if strong and vol>=1.15:return 'VOLUME_DISPLACEMENT',82
 if strong:return 'STRONG_BODY_CLOSE',76
 return '',0

def evaluate(pair,d5,d15,d1h,spread,now=None):
 for d,m in ((d5,5),(d15,15),(d1h,60)):
  ok,r=valid_candles(d,m,now)
  if not ok:return Eval(status=r,metrics={})
 x5,x15,x1=map(lambda x:add_indicators(closed(x)),(d5,d15,d1h))
 a15=x15.iloc[-1]; a1=x1.iloc[-1]
 slope15=(a15.ema20-x15.ema20.iloc[-4])/(3*max(a15.atr,1e-9))
 slope1=(a1.ema20-x1.ema20.iloc[-4])/(3*max(a1.atr,1e-9))
 long15=a15.ema20>a15.ema50 and slope15>0
 short15=a15.ema20<a15.ema50 and slope15<0
 side='LONG' if long15 else 'SHORT' if short15 else '-'
 metrics={'slope15':float(slope15),'slope1h':float(slope1),'spread':spread,'ref_price':float(x5.close.iloc[-1]),'atr5':float(x5.atr.iloc[-1]),'signal_time':str(x5.time.iloc[-1])}
 if side=='-':return Eval(status='15m trend not directional',metrics=metrics)

 # 1h is a veto only when clearly opposing; neutral 1h is allowed but scores lower.
 one_aligned=(a1.ema20>a1.ema50 and slope1>0) if side=='LONG' else (a1.ema20<a1.ema50 and slope1<0)
 one_opposed=(a1.ema20<a1.ema50 and slope1<-.04) if side=='LONG' else (a1.ema20>a1.ema50 and slope1>.04)
 if one_opposed:return Eval(side,'strong 1h opposition',metrics=metrics)

 st_ok,st,levels=structure(x15,side); metrics['structure']=st
 eff=directional_efficiency(x5,12); crosses=ema_cross_count(x5,12); ax=adx(x5)
 atr_ratio=float(x5.atr.iloc[-1]/max(x5.atr.iloc[-12],1e-9))
 metrics.update(efficiency=eff,crosses=crosses,adx=ax,atr_ratio=atr_ratio)
 # Reject only genuine multi-signal chop; marginal regime readings become score penalties.
 chop_votes=int(eff<c.MIN_EFF)+int(crosses>c.MAX_CROSSES)+int(ax<c.MIN_ADX)+int(atr_ratio<.70)
 if chop_votes>=3:return Eval(side,'severe chop/regime rejected',metrics=metrics)

 im=impulse(x5,side)
 if not im:return Eval(side,'no recent directional impulse',metrics=metrics)
 i,j,age,lo,hi,fib,intact=im; metrics.update(impulse_age=age,fib=fib)
 if not intact or not .15<=fib<=.85:return Eval(side,'invalid pullback context',metrics=metrics)

 typ,quality=confirmation(x5,side,levels); metrics.update(confirmation=typ,quality=quality)
 if not typ:return Eval(side,'no closed price-action confirmation',metrics=metrics)

 q=x5.iloc[-1]; atr=float(q.atr)
 trigger=float(q.high+.03*atr) if side=='LONG' else float(q.low-.03*atr)
 stop=float(min(q.low,x5.low.iloc[-6:].min())) if side=='LONG' else float(max(q.high,x5.high.iloc[-6:].max()))
 risk=abs(trigger-stop)
 if risk<.45*atr or risk>2.4*atr:return Eval(side,'stop quality rejected',metrics=metrics)

 targets=[z for z in levels if (z>trigger if side=='LONG' else z<trigger)]
 structural=(min(targets) if side=='LONG' else max(targets)) if targets else None
 fallback=trigger+(2.4*risk if side=='LONG' else -2.4*risk)
 target=structural if structural is not None else fallback
 gross=(target-trigger)/risk if side=='LONG' else (trigger-target)/risk
 net=gross-2*c.FEE_RATE*trigger/risk-2*c.BASE_SLIPPAGE*trigger/risk

 score=0
 score += 24                              # directional 15m trend: mandatory
 score += 16 if one_aligned else 8       # 1h confirmation/neutral
 score += 14 if st_ok else 5             # structure is confluence, not absolute veto
 score += 12 if chop_votes==0 else 8 if chop_votes==1 else 3
 score += 12 if .25<=fib<=.75 else 6
 score += min(18,quality//5)
 score += 4 if age<=8 else 2
 score=min(100,score)
 metrics.update(target=target,gross_r=gross,net_r=net,stop_distance=risk,score=score,
                one_hour_aligned=one_aligned,chop_votes=chop_votes,structural_target=structural is not None)
 if spread>c.MAX_SPREAD_PCT:return Eval(side,'spread too wide',metrics=metrics)
 if net<c.MIN_NET_R:return Eval(side,'net R rejected',metrics=metrics)
 if score<c.MIN_SCORE:return Eval(side,'confluence score rejected',metrics=metrics)
 cid=str(q.time); iid=f'{pair}:{side}:{x5.time.iloc[i]}:{x5.time.iloc[j]}'
 fp=hashlib.sha1(f'{pair}|{side}|{cid}|{iid}'.encode()).hexdigest()[:16]
 return Eval(side,'ARMED',Setup(pair,side,trigger,stop,target,atr,score,cid,fp,iid,age,fib,typ,quality,metrics,time.time()),metrics)
