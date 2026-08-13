import sys; sys.stdout.reconfigure(encoding="utf-8"); sys.path.insert(0,'.')
import numpy as np, pandas as pd
import lab.improve as I
from lab.breadth_wide import WIDE

def trades_with_times(d4, **kw):
    """bt gibi ama exit_time de dondurur."""
    out=[]
    for c,(df,ind,fs,sg,er) in d4.items():
        k=dict(kw)
        if k.get('tp_mult')=='rr': k['tp_mult']=WIDE[c][1]
        o,h,l,cl=df['open'].values,df['high'].values,df['low'].values,df['close'].values
        stop=(ind['safe_stop_pct']/100.0).values; a=I.atr(df).values
        buy,sell=fs['buy_signal'].values,fs['sell_signal'].values; n=len(df); i=0
        while i<n-1:
            if (buy[i] or sell[i]) and not (np.isnan(stop[i]) or stop[i]<=0):
                side=1 if buy[i] else -1; entry=o[i+1]*(1+I.SLIP*side); sp=stop[i]
                sl=entry*(1-sp*side); tp=entry*(1+sp*k['tp_mult']*side); risk=abs(entry-sl); best=entry
                ex=None; j=i+1
                while j<n:
                    hi,lo=h[j],l[j]; best=max(best,hi) if side==1 else min(best,lo)
                    if k['mode']=='trail' and not np.isnan(a[j]):
                        ts=best-side*k['trail_k']*a[j]; sl=max(sl,ts) if side==1 else min(sl,ts)
                    if side==1:
                        if lo<=sl: ex=sl;break
                        if k['mode']!='trail' and hi>=tp: ex=tp;break
                    else:
                        if hi>=sl: ex=sl;break
                        if k['mode']!='trail' and lo<=tp: ex=tp;break
                    j+=1
                if ex is None: ex=cl[n-1]; j=n-1
                pnl=(ex-entry)*side-entry*2*I.FEE
                out.append(dict(entry=pd.Timestamp(df.index[i+1]).tz_localize(None),
                                exit=pd.Timestamp(df.index[j]).tz_localize(None), R=pnl/risk))
                i=j+1
            else: i+=1
    out.sort(key=lambda x:x['entry']); return out

def sim(tr, start=100.0, risk=0.03, maxc=5):
    ev=[]
    for k,t in enumerate(tr):
        ev.append((t['entry'],1,k)); ev.append((t['exit'],0,k))
    ev.sort(key=lambda x:(x[0],x[1]))
    eq=start; open_r={}; curve=[(tr[0]['entry'],start)]; taken=0
    for ts,typ,k in ev:
        if typ==0 and k in open_r:
            eq+=tr[k]['R']*open_r.pop(k); curve.append((ts,eq))
        elif typ==1 and len(open_r)<maxc and eq>0:
            open_r[k]=risk*eq; taken+=1
    s=pd.Series(dict(curve)).sort_index()
    idx=pd.date_range(s.index.min().normalize(), s.index.max().normalize(), freq='D')
    d=s.reindex(idx, method='ffill').fillna(start)
    ret=d.pct_change().dropna()
    cagr=(d.iloc[-1]/d.iloc[0])**(365/len(d))-1
    return dict(final=d.iloc[-1], cagr=cagr*100, dd=(d/d.cummax()-1).min()*100,
                sharpe=ret.mean()/ret.std()*np.sqrt(365) if ret.std()>0 else 0, n=taken)

d4=I.load('4h',240)
print(f"  {'Kurulum':22} | {'son$':>8} {'CAGR':>7} {'MaxDD':>8} {'Sharpe':>7} {'alinan':>7}")
print("  "+"-"*66)
for tag,kw in [('BASELINE (sabit TP)',dict(tp_mult='rr',mode='fixed')),
               ('Trailing 4xATR',dict(tp_mult='rr',mode='trail',trail_k=4.0)),
               ('Trailing 5xATR',dict(tp_mult='rr',mode='trail',trail_k=5.0)),
               ('Trailing 6xATR',dict(tp_mult='rr',mode='trail',trail_k=6.0))]:
    tr=trades_with_times(d4,**kw)
    if not tr: continue
    r=sim(tr)
    print(f"  {tag:22} | {r['final']:8.2f} {r['cagr']:6.1f}% {r['dd']:7.1f}% {r['sharpe']:7.2f} {r['n']:7d}")
