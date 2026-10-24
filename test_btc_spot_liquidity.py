import copy
import json
import tempfile
import unittest
from pathlib import Path
from btc_spot_liquidity import normalize, collect, check, write

NOW = 1800000000000


def fixture(exchange):
    bids, asks = [['99', '2'], ['98', '3']], [['101', '4'], ['102', '5']]
    if exchange == 'bybit':
        return {'retCode': 0, 'result': {'s': 'BTCUSDT', 'ts': NOW, 'b': bids, 'a': asks}}
    return {'code': '0', 'data': [{'ts': str(NOW), 'bids': bids, 'asks': asks}]}


class LiquidityTests(unittest.TestCase):
    def test_both_spot_adapters_and_notional(self):
        for exchange in ('bybit', 'okx'):
            book = normalize(exchange, fixture(exchange), NOW)
            self.assertEqual(book['mid_usdt'], 100)
            self.assertEqual(book['bands'][-1]['bid_usdt'], 198)
            self.assertEqual(book['bands'][-1]['ask_usdt'], 404)
            self.assertTrue(book['bands'][-1]['bid_coverage_complete'])
            self.assertEqual(book['market'], 'spot')

    def test_capped_depth_is_marked_partial(self):
        payload = fixture('bybit')
        payload['result']['b'] = [['99.99', '1']]
        payload['result']['a'] = [['100.01', '1']]
        book = normalize('bybit', payload, NOW)
        self.assertFalse(book['bands'][-1]['bid_coverage_complete'])
        self.assertFalse(book['bands'][-1]['ask_coverage_complete'])

    def test_stale_future_empty_nan_duplicate_crossed_unsorted(self):
        for field, value in [('ts', NOW - 61000), ('ts', NOW + 6000), ('b', []),
                             ('b', [['NaN', '1']]), ('b', [['99', '-1']]),
                             ('b', [['99', '1'], ['99', '2']]),
                             ('b', [['102', '1']]), ('b', [['98', '1'], ['99', '1']]),
                             ('s', 'ETHUSDT')]:
            payload = fixture('bybit')
            payload['result'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                normalize('bybit', payload, NOW)

    def test_api_errors(self):
        for exchange, payload in [('bybit', {'retCode': 10001}), ('okx', {'code': '50000'})]:
            with self.assertRaises(ValueError):
                normalize(exchange, payload, NOW)

    def test_partial_failure_and_retries(self):
        calls = []
        def fetcher(url):
            calls.append(url)
            if 'bybit' in url:
                raise OSError('blocked')
            return fixture('okx')
        snapshot = collect(fetcher, lambda: NOW / 1000, lambda _: None)
        self.assertEqual(snapshot['status'], 'limited')
        self.assertEqual(len(calls), 4)
        self.assertEqual(check(snapshot, NOW), 0)

    def test_all_failure_overwrites_success_and_fails_gate(self):
        snapshot = collect(lambda _: {'code': 'bad', 'retCode': 1}, lambda: NOW / 1000, lambda _: None)
        self.assertEqual(snapshot['status'], 'unavailable')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'latest.json'
            path.write_text('{"status":"fresh"}')
            write(snapshot, path)
            self.assertEqual(json.loads(path.read_text())['status'], 'unavailable')
        with self.assertRaises(ValueError):
            check(snapshot, NOW)

    def test_consumption_rechecks_source_not_only_file(self):
        snapshot = collect(lambda url: fixture('bybit' if 'bybit' in url else 'okx'), lambda: NOW / 1000, lambda _: None)
        with self.assertRaises(ValueError):
            check(snapshot, NOW + 2701000)
        fresh_file = copy.deepcopy(snapshot)
        fresh_file['generated_at_ms'] = NOW + 2701000
        with self.assertRaises(ValueError):
            check(fresh_file, NOW + 2701000)


if __name__ == '__main__':
    unittest.main()
