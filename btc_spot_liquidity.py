"""Public BTC/USDT spot depth snapshots; no credentials or trading endpoints."""
import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URLS = {
    'bitget': 'https://api.bitget.com/api/v3/market/orderbook?category=SPOT&symbol=BTCUSDT&limit=200',
    'okx': 'https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=400',
}
MAX_SOURCE_AGE = 60
MAX_FILE_AGE = 2700


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def number(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError('Non-positive or non-finite depth value')
    return result


def normalize(exchange, payload, now_ms):
    if exchange == 'bitget':
        if payload.get('code') != '00000':
            raise ValueError('Bitget rejected request')
        book = payload['data']
        bids, asks, timestamp = book['b'], book['a'], int(book['ts'])
    elif exchange == 'okx':
        if payload.get('code') != '0' or len(payload.get('data', [])) != 1:
            raise ValueError('OKX rejected request or empty data')
        book = payload['data'][0]
        bids, asks, timestamp = book['bids'], book['asks'], int(book['ts'])
    else:
        raise ValueError('Unsupported exchange')
    age = (now_ms - timestamp) / 1000
    if not -5 <= age <= MAX_SOURCE_AGE:
        raise ValueError('Stale or future exchange timestamp')
    sides = []
    for rows, reverse in ((bids, True), (asks, False)):
        levels = [[number(row[0]), number(row[1])] for row in rows]
        if not levels or len({p for p, _ in levels}) != len(levels):
            raise ValueError('Empty or duplicate depth levels')
        if levels != sorted(levels, reverse=reverse):
            raise ValueError('Unsorted depth')
        sides.append(levels)
    bids, asks = sides
    if bids[0][0] >= asks[0][0]:
        raise ValueError('Crossed or locked book')
    mid = (bids[0][0] + asks[0][0]) / 2
    bands = []
    for bps in (10, 25, 50, 100):
        lower, upper = mid * (1 - bps / 10000), mid * (1 + bps / 10000)
        bands.append({
            'distance_bps': bps,
            'bid_usdt': sum(p * q for p, q in bids if p >= lower),
            'ask_usdt': sum(p * q for p, q in asks if p <= upper),
            'bid_coverage_complete': bids[-1][0] <= lower,
            'ask_coverage_complete': asks[-1][0] >= upper,
        })
    return {
        'status': 'fresh', 'exchange': exchange, 'market': 'spot',
        'symbol': 'BTC/USDT', 'source_url': URLS[exchange],
        'source_timestamp_ms': timestamp, 'source_timestamp_utc': utc(timestamp),
        'received_at_ms': now_ms, 'source_age_seconds_at_receipt': age,
        'mid_usdt': mid, 'spread_bps': (asks[0][0] - bids[0][0]) / mid * 10000,
        'bids': bids, 'asks': asks, 'bands': bands,
        'largest_bid_levels': sorted(bids, key=lambda v: v[0] * v[1], reverse=True)[:10],
        'largest_ask_levels': sorted(asks, key=lambda v: v[0] * v[1], reverse=True)[:10],
    }


def fetch(url):
    request = Request(url, headers={'User-Agent': 'SS-CRYPTO-public-depth/1.0', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def collect(fetcher=fetch, clock=time.time, sleeper=time.sleep):
    exchanges = {}
    for exchange, url in URLS.items():
        for attempt in range(3):
            try:
                payload = fetcher(url)
                exchanges[exchange] = normalize(exchange, payload, int(clock() * 1000))
                break
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                exchanges[exchange] = {'status': 'unavailable', 'error': type(exc).__name__ + ': ' + str(exc)[:200]}
                if attempt < 2:
                    sleeper(2 ** attempt)
    available = sum(v['status'] == 'fresh' for v in exchanges.values())
    now_ms = int(clock() * 1000)
    return {
        'schema_version': 1, 'generated_at_ms': now_ms, 'generated_at_utc': utc(now_ms),
        'status': 'fresh' if available == 2 else 'limited' if available else 'unavailable',
        'kind': 'sampled_spot_orderbook', 'exchanges': exchanges,
        'limitations': 'Visible capped depth only; partial bands are lower bounds. No liquidation heatmap, hidden orders, persistence proof, or trade signal. Recheck source timestamps at consumption.',
    }


def check(snapshot, now_ms, max_age=MAX_FILE_AGE):
    age = (now_ms - snapshot['generated_at_ms']) / 1000
    if snapshot['status'] not in ('fresh', 'limited') or not -5 <= age <= max_age:
        raise ValueError('Unusable or stale snapshot')
    usable = 0
    for exchange in URLS:
        book = snapshot['exchanges'][exchange]
        if book['status'] == 'fresh':
            source_age = (now_ms - book['source_timestamp_ms']) / 1000
            if not -5 <= source_age <= max_age:
                raise ValueError('Stale or future source at consumption')
            usable += 1
    if usable == 0 or (snapshot['status'] == 'fresh' and usable != 2):
        raise ValueError('Inconsistent availability')
    return age


def write(snapshot, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/btc_spot_liquidity.json')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--max-age-seconds', type=int, default=MAX_FILE_AGE)
    args = parser.parse_args()
    if args.max_age_seconds <= 0:
        parser.error('max age must be positive')
    if args.check:
        snapshot = json.loads(Path(args.output).read_text(encoding='utf-8'))
    else:
        snapshot = collect()
        write(snapshot, args.output)  # Replace old success even when every source fails.
    age = check(snapshot, int(time.time() * 1000), args.max_age_seconds)
    print(json.dumps({'status': snapshot['status'], 'age_seconds': round(age, 3),
                      'sources': {k: v['status'] for k, v in snapshot['exchanges'].items()}}))


if __name__ == '__main__':
    main()
