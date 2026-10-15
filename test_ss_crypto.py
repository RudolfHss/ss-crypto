"""Synthetic deterministic fixtures; live reports never use these test prices."""
import copy
import datetime as dt
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

from ss_crypto_analysis import UTC, PERIODS, boundary, expected_close, age_status, validate_candles, indicators, structure, ema
import ss_crypto_market_data as collector
from ss_crypto_daily_report import UNIVERSE, UNIVERSE_VERSION, build_model, validate_sample, compare, export, verify_outputs
from ss_crypto_pipeline import schedule_decision

NOW=dt.datetime(2026,10,15,7,30,tzinfo=UTC)

def candles(tf='4H',count=1000,now=NOW):
    seconds=PERIODS[tf];end=expected_close(tf,now)
    rows=[]
    for i in range(count):
        start=end-dt.timedelta(seconds=(count-i)*seconds)
        price=100+i*.01+math.sin(i/3)
        rows.append({'open_time_utc':start.isoformat(),'open_time_ms':int(start.timestamp()*1000),'open':price,'high':price+1,'low':price-1,'close':price,'volume_base':10})
    return rows

def sample(now=NOW):
    return {'schema_version':1,'source':'CoinGecko /global','observed_at':now.isoformat(),'source_updated_at':(now-dt.timedelta(minutes=5)).isoformat(),'values':{'BTC.D':60,'ETH.D':10,'USDT.D':5,'USDC.D':3,'TOTAL':1000,'TOTAL2':400,'TOTAL3':300}}

def context(now=NOW):
    ts=now.isoformat();observations=[{'id':id,'return_24h_pct':1 if i<6 else -1,'source_updated_at':ts} for i,id in enumerate(UNIVERSE)]
    return {'schema_version':1,'source':'CoinGecko /coins/markets','observed_at':ts,'universe_version':UNIVERSE_VERSION,'universe':UNIVERSE,'components':{'stablecoin_caps':{'status':'available','values':{s:{'usd':10,'source_updated_at':ts} for s in ['USDT','USDC']}},'eth_btc':{'status':'available','ratio':.05,'relative_change_24h_pct':1,'source_updated_at':ts},'breadth':{'status':'available','advancing':6,'denominator':12,'coverage':12,'positive_pct':50,'observations':observations}}}

def dataset(now=NOW):
    return {'status':'ok','exchange':'Coinbase','market':'BTC/USDT','retrieved_at_utc':now.isoformat(),'timeframes':{tf:candles(tf,1000 if tf!='1W' else 230,now) for tf in PERIODS}}

def write_inputs(root,btc=None,dominance=None,ctx=None):
    root=Path(root);(root/'data/dominance').mkdir(parents=True,exist_ok=True)
    d=dominance or sample()
    for path,value in [('ss_crypto_btc_ohlcv.json',btc or dataset()),('ss_crypto_dominance_latest.json',d),('ss_crypto_context.json',ctx or context()),('data/dominance/2026-10.json',[d])]:
        (root/path).write_text(json.dumps(value),encoding='utf-8')

class ClockAndQualityTests(unittest.TestCase):
    def test_budapest_dst_and_delayed_daily_schedule(self):
        for day,hour in [('2026-03-28',6),('2026-03-29',5),('2026-10-24',5),('2026-10-25',6)]:
            now=dt.datetime.fromisoformat(day+'T09:00:00+00:00')
            self.assertTrue(schedule_decision(now,f'30 {hour} * * *')[0])
            self.assertFalse(schedule_decision(now,f'30 {11-hour} * * *')[0])
            self.assertFalse(schedule_decision(now,f'30 {hour} * * *',True)[0])
            self.assertFalse(schedule_decision(now.replace(hour=hour,minute=29),f'30 {hour} * * *')[0])
    def test_daily_grace_boundary(self):
        self.assertEqual(expected_close('1D',dt.datetime(2026,10,15,0,4,tzinfo=UTC)),dt.datetime(2026,10,14,tzinfo=UTC))
        self.assertEqual(expected_close('1D',dt.datetime(2026,10,15,0,5,tzinfo=UTC)),dt.datetime(2026,10,15,tzinfo=UTC))

    def test_weekly_boundary_never_requires_unclosed_week(self):
        self.assertEqual(expected_close('1W',dt.datetime(2026,10,18,23,59,tzinfo=UTC)),dt.datetime(2026,10,12,tzinfo=UTC))
        self.assertEqual(expected_close('1W',dt.datetime(2026,10,19,0,4,tzinfo=UTC)),dt.datetime(2026,10,12,tzinfo=UTC))
        self.assertEqual(expected_close('1W',dt.datetime(2026,10,19,0,5,tzinfo=UTC)),dt.datetime(2026,10,19,tzinfo=UTC))

    def test_exact_freshness_limits(self):
        for seconds,want in [(5400,'friss'),(5401,'korlátozott'),(86400,'korlátozott'),(86401,'nem értékelhető')]:self.assertEqual(age_status(NOW-dt.timedelta(seconds=seconds),NOW,5400)[0],want)
        self.assertEqual(age_status(NOW-dt.timedelta(seconds=7200),NOW,7200)[0],'friss')
        with self.assertRaises(ValueError):age_status(NOW+dt.timedelta(seconds=301),NOW,5400)

    def test_timezone_required(self):
        from ss_crypto_analysis import timestamp
        with self.assertRaises(ValueError):timestamp('2026-10-15T07:30:00')

class CandleTests(unittest.TestCase):
    def test_weekly_gap_rejected(self):
        rows=candles('1W',230);rows.pop(100)
        with self.assertRaisesRegex(ValueError,'gap'):validate_candles(rows,'1W',NOW)

    def test_non_utc_daily_alignment_rejected(self):
        rows=candles('1D')
        for r in rows:
            from ss_crypto_analysis import timestamp
            t=timestamp(r['open_time_utc'])+dt.timedelta(hours=8);r['open_time_utc']=t.isoformat();r['open_time_ms']=int(t.timestamp()*1000)
        with self.assertRaisesRegex(ValueError,'boundary'):validate_candles(rows,'1D',NOW)

    def test_future_open_duplicate_and_invalid_rows(self):
        for mutate in [lambda r:r.append(copy.deepcopy(r[-1])),lambda r:r[-1].update(volume_base=float('nan')),lambda r:r[-1].update(low=9999),lambda r:r[-1].update(open_time_ms=1)]:
            rows=candles();mutate(rows)
            with self.assertRaises(ValueError):validate_candles(rows,'4H',NOW)
        rows=candles(now=NOW+dt.timedelta(hours=4))
        with self.assertRaisesRegex(ValueError,'open candle'):validate_candles(rows,'4H',NOW)

    def test_okx_explicit_utc_bars_and_pagination(self):
        rows=candles('1D');raw=[[str(r['open_time_ms']),str(r['open']),str(r['high']),str(r['low']),str(r['close']),'10','0','0','1'] for r in rows][::-1]
        def fake(url):
            q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            self.assertEqual(q['bar'],['1Dutc']);self.assertEqual(q['limit'],['100'])
            after=int(q.get('after',[10**18])[0]);return {'code':'0','data':[r for r in raw if int(r[0])<after][:100]}
        with patch.object(collector,'get',side_effect=fake),patch.object(collector.time,'sleep'):
            got=collector.okx('1D',NOW)
        self.assertEqual(len(got),1000);self.assertEqual(collector.OKX_BARS['1W'],'1Wutc')

    def test_collector_old_last_closed_rejected(self):
        rows=candles('1D',1001)[:-1]
        raw=[[r['open_time_ms'],r['open'],r['high'],r['low'],r['close'],r['volume_base']] for r in rows]
        with self.assertRaisesRegex(ValueError,'differs'):collector.normalize(raw,'1D',NOW)

class IndicatorTests(unittest.TestCase):
    def test_ema_independent_closed_form_decimal_reference(self):
        values=[100+math.sin(i/17)*20+i*.01 for i in range(1100)]
        with localcontext() as ctx:
            ctx.prec=50;a=Decimal(2)/Decimal(201);b=1-a
            ref=Decimal(str(values[0]))*b**(len(values)-1)+sum(a*b**(len(values)-1-i)*Decimal(str(v)) for i,v in enumerate(values[1:],1))
        self.assertAlmostEqual(ema(values,200)[-1],float(ref),places=10)

    def test_flat_indicators_and_volume_denominator_excludes_current(self):
        rows=candles()
        for r in rows:r.update(open=100,close=100,high=101,low=99,volume_base=10)
        rows[-1]['volume_base']=20
        m=indicators(rows,'4H')
        self.assertEqual(m['rsi14'],50);self.assertEqual(m['macd_hist'],0);self.assertEqual(m['atr14'],2);self.assertEqual(m['rvol20'],2)

    def test_short_history_does_not_publish_ema200(self):
        self.assertIsNone(indicators(candles('1W',230),'1W')['ema200'])
        self.assertIsNotNone(indicators(candles(),'4H')['ema200'])
        self.assertLess(indicators(candles(),'4H')['ema200_seed_weight'],.00005)

    def test_confirmed_swing_structure_and_no_endpoint_lookahead(self):
        prices=[10,12,15,12,11,13,17,14,12,15,19,16,14,17,21,18,16]
        rows=candles(count=len(prices))
        for row,price in zip(rows,prices):row.update(open=price,close=price,high=price+.1,low=price-.1)
        self.assertEqual(structure(rows,'4H')['state'],'emelkedő (HH/HL)')
        before=structure(rows[:-2],'4H');after=structure(rows,'4H')
        self.assertNotIn(rows[-3]['open_time_utc'],[p['pivot_at'] for p in before['highs']])
        self.assertEqual(after['highs'][-1]['pivot_at'],rows[-3]['open_time_utc'])
        self.assertEqual(after['highs'][-1]['confirmed_at'],expected_close('4H',NOW).isoformat())

class ModelTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);write_inputs(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_fresh_model_and_daily_no_trade_service(self):
        m=build_model(self.root,NOW)
        self.assertEqual(m['data_status'],'friss');self.assertTrue(m['current_analysis_allowed']);self.assertFalse(m['new_trade_signal'])
        self.assertEqual(len(m['scenarios']),3);self.assertIsNone(m['dominance']['change_24h'])

    def test_stale_data_disables_current_scenarios(self):
        m=build_model(self.root,NOW+dt.timedelta(hours=3))
        self.assertEqual(m['data_status'],'korlátozott');self.assertFalse(m['current_analysis_allowed']);self.assertTrue(m['historical_summary_only'])
        self.assertTrue(all(s['condition_observed'] is None for s in m['scenarios']))
        self.assertEqual(build_model(self.root,NOW+dt.timedelta(hours=25))['data_status'],'nem értékelhető')

    def test_missing_latest_candle_despite_fresh_request(self):
        b=dataset();b['timeframes']['4H']=candles(count=1001)[:-1];write_inputs(self.root,btc=b)
        m=build_model(self.root,NOW);self.assertEqual(m['btc']['timeframes']['4H']['status'],'korlátozott');self.assertFalse(m['current_analysis_allowed'])

    def test_missing_or_corrupt_inputs_emit_non_evaluable_report(self):
        (self.root/'ss_crypto_btc_ohlcv.json').write_text('broken')
        m=build_model(self.root,NOW);self.assertEqual(m['data_status'],'nem értékelhető');self.assertFalse(m['new_trade_signal'])
        self.assertFalse(m['current_analysis_allowed'])

    def test_missing_breadth_never_becomes_total3(self):
        ctx=context();ctx['components']['breadth']['observations'].pop();write_inputs(self.root,ctx=ctx)
        m=build_model(self.root,NOW);self.assertEqual(m['context']['status'],'korlátozott');self.assertIsNone(m['context']['components']['breadth']['data']);self.assertFalse(m['current_analysis_allowed'])

    def test_source_switch_blocks_previous_level_comparison(self):
        prior=build_model(self.root,NOW)
        b=dataset(NOW+dt.timedelta(minutes=1));b['exchange']='OKX';write_inputs(self.root,btc=b)
        m=build_model(self.root,NOW+dt.timedelta(minutes=2),previous=prior)
        self.assertTrue(m['source_changed']);self.assertFalse(m['previous_report_comparison']['available'])

    def test_same_exchange_previous_report_level_change(self):
        prior=build_model(self.root,NOW)
        m=build_model(self.root,NOW+dt.timedelta(minutes=1),previous=prior)
        self.assertTrue(m['previous_report_comparison']['available']);self.assertEqual(m['previous_report_comparison']['level_changes']['ema20'],0)

    def test_dominance_change_units_and_no_fake_reference(self):
        latest=sample();before=sample(NOW-dt.timedelta(hours=24));before['values']['BTC.D']=59;before['values']['TOTAL']=1000/1.1
        change=compare(latest,[before]);self.assertAlmostEqual(change['changes']['BTC.D'],1);self.assertAlmostEqual(change['changes']['TOTAL'],10)
        self.assertIsNone(compare(latest,[sample(NOW-dt.timedelta(hours=30))]))

    def test_invalid_dominance_fails_closed(self):
        for mutate in [lambda s:s['values'].pop('USDC.D'),lambda s:s['values'].update(TOTAL3=10),lambda s:s['values'].update(TOTAL=float('nan'))]:
            d=sample();mutate(d)
            with self.assertRaises(ValueError):validate_sample(d)

    def test_future_sample_cannot_enter_report(self):
        write_inputs(self.root,dominance=sample(NOW+dt.timedelta(hours=1)))
        self.assertEqual(build_model(self.root,NOW)['data_status'],'nem értékelhető')

    def test_failed_collection_prevents_current_recommendation_even_if_retained_data_is_recent(self):
        (self.root/'provenance.json').write_text(json.dumps({'collection_failures':['btc']}))
        m=build_model(self.root,NOW)
        self.assertEqual(m['data_status'],'korlátozott');self.assertFalse(m['current_analysis_allowed'])
        self.assertTrue(all(s['condition_observed'] is None for s in m['scenarios']))

    def test_export_same_document_model_not_page_count(self):
        m=build_model(self.root,NOW,test_report=True)
        path=export(m,self.root/'reports',pdf=True)
        verify_outputs(path)
        reloaded=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(reloaded['document'],m['document']);self.assertEqual(reloaded['content_sha256'],m['content_sha256'])

if __name__=='__main__':unittest.main()
