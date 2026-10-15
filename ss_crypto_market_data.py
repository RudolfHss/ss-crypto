#!/usr/bin/env python3
"""Closed UTC BTC/USDT candles, with one exchange for the entire dataset."""
import datetime as dt
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from ss_crypto_analysis import UTC, PERIODS, boundary, expected_close, validate_candles

COUNTS={'4H':1000,'1D':1000,'1W':600}
MINIMUMS={'4H':1000,'1D':1000,'1W':200}
TIMEFRAMES=PERIODS
OKX_BARS={'4H':'4H','1D':'1Dutc','1W':'1Wutc'}

def get(url):
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'SS-CRYPTO/2.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=25) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in [429,500,502,503,504] or attempt==2:raise
        except (urllib.error.URLError,TimeoutError):
            if attempt==2:raise
        time.sleep(2*(attempt+1))

def iso(seconds):return dt.datetime.fromtimestamp(seconds,UTC).isoformat()

def normalize(rows,tf,now=None):
    now=now or dt.datetime.now(UTC)
    end=expected_close(tf,now)
    unique={}
    for raw in rows:
        t,o,h,l,c,v=raw[:6]
        t=int(t);t=t//1000 if t>10**11 else t
        row={'open_time_utc':iso(t),'open_time_ms':t*1000,'open':float(o),'high':float(h),'low':float(l),'close':float(c),'volume_base':float(v)}
        if t+PERIODS[tf] > end.timestamp():continue
        if t in unique and unique[t]!=row:raise ValueError('Conflicting duplicate candle')
        unique[t]=row
    out=[unique[t] for t in sorted(unique)][-COUNTS[tf]:]
    last=validate_candles(out,tf,now,MINIMUMS[tf])
    if last!=end:raise ValueError(f'{tf}: last close {last} differs from expected {end}')
    return out

def coinbase(tf,now=None):
    now=now or dt.datetime.now(UTC)
    seconds=PERIODS[tf];granularity=3600 if tf=='4H' else 86400
    end=int(expected_close(tf,now).timestamp());start=end-COUNTS[tf]*seconds
    candles={};cursor=start
    while cursor<end:
        page_end=min(cursor+250*granularity,end)
        params=urllib.parse.urlencode({'granularity':granularity,'start':iso(cursor),'end':iso(page_end)})
        data=get('https://api.exchange.coinbase.com/products/BTC-USDT/candles?'+params)
        if not isinstance(data,list):raise ValueError('Invalid Coinbase response')
        for t,l,h,o,c,v in data:
            t=int(t)
            if cursor<=t<page_end:
                row=[t,float(o),float(h),float(l),float(c),float(v)]
                if t in candles and candles[t]!=row:raise ValueError('Conflicting Coinbase candle')
                candles[t]=row
        cursor=page_end;time.sleep(.12)
    rows=[];started=False
    for bucket in range(start,end,seconds):
        times=list(range(bucket,bucket+seconds,granularity))
        if not all(t in candles for t in times):
            # Short weekly listing history may omit a prefix, never an interior gap.
            if tf=='1W' and not started:continue
            raise ValueError(f'Coinbase incomplete {tf} bucket {iso(bucket)}')
        started=True;parts=[candles[t] for t in times]
        # Validate every underlying candle too, before aggregation can conceal it.
        for r in parts:
            if not 0<r[3]<=min(r[1],r[4])<=max(r[1],r[4])<=r[2] or r[5]<0:raise ValueError('Invalid Coinbase constituent')
        rows.append([bucket,parts[0][1],max(r[2] for r in parts),min(r[3] for r in parts),parts[-1][4],sum(r[5] for r in parts)])
    return normalize(rows,tf,now)

def okx(tf,now=None):
    now=now or dt.datetime.now(UTC);rows=[];after=None
    while len(rows)<COUNTS[tf]:
        params={'instId':'BTC-USDT','bar':OKX_BARS[tf],'limit':100}
        if after is not None:params['after']=after
        payload=get('https://www.okx.com/api/v5/market/history-candles?'+urllib.parse.urlencode(params))
        if payload.get('code')!='0':raise ValueError('OKX request rejected')
        page=payload.get('data',[])
        if not page:break
        oldest=min(int(r[0]) for r in page)
        if after is not None and oldest>=int(after):raise ValueError('OKX pagination did not advance')
        after=str(oldest)
        rows.extend(r[:6] for r in page if str(r[8])=='1' and int(r[0])/1000+PERIODS[tf]<=expected_close(tf,now).timestamp())
        time.sleep(.12)
    return normalize(rows,tf,now)

def bybit(tf,now=None):
    now=now or dt.datetime.now(UTC);rows=[];end=int(expected_close(tf,now).timestamp()*1000)-1
    while len(rows)<COUNTS[tf]:
        params={'category':'spot','symbol':'BTCUSDT','interval':{'4H':'240','1D':'D','1W':'W'}[tf],'limit':1000,'end':end}
        payload=get('https://api.bybit.com/v5/market/kline?'+urllib.parse.urlencode(params))
        if payload.get('retCode')!=0:raise ValueError('Bybit request rejected')
        page=payload.get('result',{}).get('list',[])
        if not page:break
        oldest=min(int(r[0]) for r in page)
        if oldest>end:raise ValueError('Bybit pagination did not advance')
        rows.extend(page);end=oldest-1;time.sleep(.12)
    return normalize(rows,tf,now)

def main():
    path=Path('ss_crypto_btc_ohlcv.json');previous=None
    if path.exists():
        try:previous=json.loads(path.read_text(encoding='utf-8')).get('exchange')
        except (ValueError,OSError):pass
    failures=[];as_of=dt.datetime.now(UTC)
    for name,fn in [('Coinbase',coinbase),('OKX',okx),('Bybit',bybit)]:
        try:
            frames={tf:fn(tf,as_of) for tf in PERIODS}
            result={'schema_version':2,'status':'ok','exchange':name,'previous_exchange':previous,'source_changed':previous is not None and previous!=name,'market':'BTC/USDT','market_type':'spot','retrieved_at_utc':dt.datetime.now(UTC).isoformat(),'collection_as_of_utc':as_of.isoformat(),'timezone':'UTC; daily 00:00; weekly Monday 00:00','requested_counts':COUNTS,'actual_counts':{tf:len(rows) for tf,rows in frames.items()},'ema200_minimum':1000,'timeframes':frames,'failed_sources':failures,'volume_method':'base BTC volume; one exchange only; no cross-exchange volume comparison'}
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
            print(json.dumps({'exchange':name,'counts':result['actual_counts'],'source_changed':result['source_changed']}));return 0
        except Exception as error:
            failures.append({'exchange':name,'reason':f'{type(error).__name__}: {error}'})
            print(f'{name}: {error}',file=sys.stderr)
    print(json.dumps({'status':'no_verified_data','failed_sources':failures}));return 1

if __name__=='__main__':sys.exit(main())
