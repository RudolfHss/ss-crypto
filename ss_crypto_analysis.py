"""Deterministic, point-in-time SS CRYPTO data quality and analysis rules."""
import datetime as dt
import math

UTC = dt.timezone.utc
PERIODS = {'4H': 14400, '1D': 86400, '1W': 604800}
CLOSE_GRACE_SECONDS = 300
EMA200_MINIMUM = 1000
MINIMUM_CANDLES = 200
QUALITY = {'friss': 0, 'korlátozott': 1, 'nem értékelhető': 2}

def timestamp(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('Timezone required')
    return result.astimezone(UTC)

def utc(value=None):
    return value if value is not None else dt.datetime.now(UTC)

def boundary(tf, at):
    seconds = PERIODS[tf]
    offset = 4 * 86400 if tf == '1W' else 0
    return dt.datetime.fromtimestamp(((int(at.timestamp()) - offset) // seconds) * seconds + offset, UTC)

def expected_close(tf, at):
    return boundary(tf, at - dt.timedelta(seconds=CLOSE_GRACE_SECONDS))

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def age_status(source_at, now, fresh_seconds):
    age = (now - source_at).total_seconds()
    if age < -300: raise ValueError('Future timestamp')
    return ('friss' if age <= fresh_seconds else 'korlátozott' if age <= 86400 else 'nem értékelhető'), max(0, age)

def validate_candles(rows, tf, collected_at, minimum=MINIMUM_CANDLES):
    if not isinstance(rows, list) or len(rows) < minimum: raise ValueError(f'{tf}: insufficient history ({len(rows) if isinstance(rows,list) else 0}/{minimum})')
    previous = None
    for row in rows:
        start = timestamp(row['open_time_utc'])
        if boundary(tf, start) != start: raise ValueError(f'{tf}: non-UTC candle boundary')
        if row.get('open_time_ms', int(start.timestamp()*1000)) != int(start.timestamp()*1000): raise ValueError(f'{tf}: inconsistent timestamp')
        if previous and (start-previous).total_seconds() != PERIODS[tf]: raise ValueError(f'{tf}: candle gap or duplicate')
        if start + dt.timedelta(seconds=PERIODS[tf]) > collected_at: raise ValueError(f'{tf}: open candle')
        if any(not finite(row[k]) for k in ['open','high','low','close','volume_base']): raise ValueError(f'{tf}: nonfinite OHLCV')
        if not 0 < row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high'] or row['volume_base'] < 0: raise ValueError(f'{tf}: invalid OHLCV')
        previous = start
    return timestamp(rows[-1]['open_time_utc']) + dt.timedelta(seconds=PERIODS[tf])

def ema(values, length):
    result = [values[0]]
    for value in values[1:]: result.append(result[-1] + 2/(length+1)*(value-result[-1]))
    return result

def structure(rows, tf, left=2, right=2):
    # A pivot exists for this evaluation only after the right-hand candles CLOSE.
    pivots = {'highs': [], 'lows': []}
    for i in range(left, len(rows)-right):
        for key, field, is_extreme in [('highs','high',lambda a,b:a>b), ('lows','low',lambda a,b:a<b)]:
            value = rows[i][field]
            neighbours = rows[i-left:i] + rows[i+1:i+right+1]
            if all(is_extreme(value,r[field]) for r in neighbours):
                pivots[key].append({'price':value,'pivot_at':rows[i]['open_time_utc'],'confirmed_at':(timestamp(rows[i+right]['open_time_utc'])+dt.timedelta(seconds=PERIODS[tf])).isoformat()})
    highs, lows = pivots['highs'][-2:], pivots['lows'][-2:]
    state = 'nem eldönthető'
    if len(highs)==len(lows)==2:
        dh, dl = highs[-1]['price']-highs[-2]['price'], lows[-1]['price']-lows[-2]['price']
        state = 'emelkedő (HH/HL)' if dh>0 and dl>0 else 'eső (LH/LL)' if dh<0 and dl<0 else 'vegyes / sávos'
    return {'state':state,'left':left,'right':right,'highs':highs,'lows':lows,'method':'strict 2-left/2-right confirmed pivots; no unconfirmed endpoint pivots'}

def indicators(rows, tf):
    close = [r['close'] for r in rows]
    diff = [b-a for a,b in zip(close,close[1:])]
    gain = sum(max(x,0) for x in diff[:14])/14
    loss = sum(max(-x,0) for x in diff[:14])/14
    for x in diff[14:]: gain=(gain*13+max(x,0))/14; loss=(loss*13+max(-x,0))/14
    tr = [max(r['high']-r['low'],abs(r['high']-close[i-1]),abs(r['low']-close[i-1])) for i,r in enumerate(rows) if i]
    atr = sum(tr[:14])/14
    for x in tr[14:]: atr=(atr*13+x)/14
    macd = [a-b for a,b in zip(ema(close,12),ema(close,26))]
    signal = ema(macd,9)[-1]
    average_volume = sum(r['volume_base'] for r in rows[-21:-1])/20
    e20,e50=ema(close,20)[-1],ema(close,50)[-1]
    return {'close':close[-1],'change_pct':(close[-1]/close[-2]-1)*100,'ema20':e20,'ema50':e50,'ema200':ema(close,200)[-1] if len(rows)>=EMA200_MINIMUM else None,'ema200_samples':len(rows),'ema200_seed_weight':(199/201)**(len(rows)-1),'ema_order':'ár > EMA20 > EMA50' if close[-1]>e20>e50 else 'ár < EMA20 < EMA50' if close[-1]<e20<e50 else 'vegyes EMA-sorrend','rsi14':50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss),'atr14':atr,'macd':macd[-1],'macd_signal':signal,'macd_hist':macd[-1]-signal,'rvol20':rows[-1]['volume_base']/average_volume if average_volume>0 else None,'structure':structure(rows,tf)}

def analyse_btc(dataset, now):
    if dataset.get('status')!='ok' or dataset.get('market')!='BTC/USDT' or dataset.get('exchange') not in ['Coinbase','OKX','Bybit']: raise ValueError('Invalid BTC dataset')
    collected=timestamp(dataset['retrieved_at_utc'])
    status,age=age_status(collected,now,5400)
    result={'status':status,'exchange':dataset['exchange'],'market':'BTC/USDT spot','retrieved_at_utc':collected.isoformat(),'age_seconds':age,'timeframes':{},'reasons':[]}
    if status!='friss':result['reasons'].append('A BTC-lekérés 90 percnél régebbi.' if age<=86400 else 'A BTC-lekérés 24 óránál régebbi.')
    for tf in PERIODS:
        try:
            rows=dataset['timeframes'][tf]
            last=validate_candles(rows,tf,collected)
            if last>boundary(tf,now):raise ValueError('Candle unavailable at evaluation time')
            expected=expected_close(tf,now)
            tf_status=status
            reasons=[]
            if last<expected:
                tf_status=max([tf_status,'korlátozott'],key=QUALITY.get)
                reasons.append('Hiányzik az utolsó elvárt lezárt gyertya.')
            if last>boundary(tf,collected):raise ValueError('Invalid close timestamp')
            result['timeframes'][tf]={'status':tf_status,'reasons':reasons,'count':len(rows),'last_close_utc':last.isoformat(),'expected_close_utc':expected.isoformat(),'expected_at_collection_utc':expected_close(tf,collected).isoformat(),'indicators':indicators(rows,tf)}
        except (ValueError,KeyError,TypeError) as error:
            result['timeframes'][tf]={'status':'nem értékelhető','reasons':[str(error)],'expected_close_utc':expected_close(tf,now).isoformat(),'indicators':None}
    result['status']=max([result['status']]+[r['status'] for r in result['timeframes'].values()],key=QUALITY.get)
    daily=dataset.get('timeframes',{}).get('1D',[])
    four=dataset.get('timeframes',{}).get('4H',[])
    if result['timeframes']['1D']['indicators']:
        result['levels']={'seven_day_low':min(r['low'] for r in daily[-7:]),'seven_day_high':max(r['high'] for r in daily[-7:]),'ema20':result['timeframes']['1D']['indicators']['ema20'],'ema50':result['timeframes']['1D']['indicators']['ema50']}
    else:result['levels']={}
    if result['timeframes']['4H']['indicators']:
        result['scenario_range']={'lower':min(r['low'] for r in four[-22:-2]),'upper':max(r['high'] for r in four[-22:-2]),'last_two_closes':[r['close'] for r in four[-2:]],'method':'20 closed 4H bars preceding the last two confirmation bars'}
    return result
