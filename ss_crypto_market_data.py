#!/usr/bin/env python3
"""SS CRYPTO: public BTC/USDT spot OHLCV collector with exchange failover.
Run in a network-enabled environment: python ss_crypto_market_data.py
"""
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

COUNT = 200
TIMEFRAMES = {'4H': 4*3600, '1D': 86400, '1W': 7*86400}
TIMEOUT = 12


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'SS-CRYPTO-data-check/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def normalize(rows, seconds):
    out = []
    for r in rows:
        t, o, h, l, c, v = r[:6]
        t = int(t)
        if t < 10**11: t *= 1000
        o, h, l, c, v = map(float, (o, h, l, c, v))
        if not (0 < l <= min(o,c) <= max(o,c) <= h and v >= 0):
            raise ValueError('Invalid OHLCV candle')
        out.append({'open_time_utc': iso(t), 'open_time_ms': t, 'open':o, 'high':h, 'low':l, 'close':c, 'volume_base':v})
    out.sort(key=lambda x: x['open_time_ms'])
    out = [x for x in out if x['open_time_ms'] + seconds*1000 <= int(time.time()*1000)]
    if len(out) < COUNT:
        raise ValueError(f'Only {len(out)} closed candles, need {COUNT}')
    out = out[-COUNT:]
    for a,b in zip(out, out[1:]):
        if b['open_time_ms'] - a['open_time_ms'] != seconds*1000 and seconds != 7*86400:
            raise ValueError('Missing/irregular candle interval')
    if int(time.time()*1000) - (out[-1]['open_time_ms'] + seconds*1000) > seconds*1000*2:
        raise ValueError('Stale candles')
    return out


def binance(tf):
    interval = {'4H':'4h','1D':'1d','1W':'1w'}[tf]
    url = 'https://api.binance.com/api/v3/klines?' + urllib.parse.urlencode({'symbol':'BTCUSDT','interval':interval,'limit':COUNT+2})
    return normalize(get(url), TIMEFRAMES[tf])


def okx(tf):
    # OKX recent candles endpoint supports up to 300 candles.
    bar = {'4H':'4H','1D':'1D','1W':'1W'}[tf]
    url = 'https://www.okx.com/api/v5/market/candles?' + urllib.parse.urlencode({'instId':'BTC-USDT','bar':bar,'limit':COUNT+2})
    payload = get(url)
    if payload.get('code') != '0': raise ValueError('OKX error: '+str(payload.get('msg')))
    # OKX rows: ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm
    rows = [r[:6] for r in payload['data'] if str(r[8]) == '1']
    return normalize(rows, TIMEFRAMES[tf])


def bybit(tf):
    interval = {'4H':'240','1D':'D','1W':'W'}[tf]
    url = 'https://api.bybit.com/v5/market/kline?' + urllib.parse.urlencode({'category':'spot','symbol':'BTCUSDT','interval':interval,'limit':COUNT+2})
    payload = get(url)
    if payload.get('retCode') != 0: raise ValueError('Bybit error: '+str(payload.get('retMsg')))
    return normalize(payload['result']['list'], TIMEFRAMES[tf])


def main():
    failures = []
    # One exchange must supply all frames, avoiding mixed-exchange indicator inputs.
    for name, fn in [('Binance',binance),('OKX',okx),('Bybit',bybit)]:
        try:
            frames = {tf: fn(tf) for tf in TIMEFRAMES}
            result = {'status':'ok','exchange':name,'market':'BTC/USDT','market_type':'spot',
                      'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                      'closed_candles_per_timeframe':COUNT,'timeframes':frames,'failed_sources':failures}
            with open('ss_crypto_btc_ohlcv.json','w',encoding='utf-8') as f:
                json.dump(result,f,ensure_ascii=False,indent=2)
            print(f'OK: {name}, {COUNT} closed candles each on 4H, 1D, 1W. Saved ss_crypto_btc_ohlcv.json')
            return 0
        except Exception as exc:
            failures.append({'exchange':name,'reason':f'{type(exc).__name__}: {exc}'})
            print(f'{name}: FAILED: {exc}', file=sys.stderr)
    print(json.dumps({'status':'no_verified_data','failed_sources':failures},ensure_ascii=False,indent=2))
    return 1


if __name__ == '__main__':
    sys.exit(main())
