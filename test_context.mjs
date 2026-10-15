import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ALT_UNIVERSE,contextSnapshot} from './ss_crypto_dominance.mjs';
const now=new Date('2026-10-15T07:30:00Z');
const rows=()=>[...new Set(['bitcoin','tether','usd-coin',...ALT_UNIVERSE])].map((id,i)=>({id,last_updated:now.toISOString(),market_cap:1000+i,current_price:id==='bitcoin'?100:id==='ethereum'?5:1,price_change_percentage_24h:id==='bitcoin'?0:id==='ethereum'?10:i%2?2:-1}));
test('ETH/BTC, actual stablecoin caps and real fixed-universe breadth',()=>{
  const r=contextSnapshot(rows(),now);
  assert.equal(r.components.eth_btc.ratio,.05);
  assert.ok(Math.abs(r.components.eth_btc.relative_change_24h_pct-10)<1e-9);
  assert.equal(r.components.stablecoin_caps.values.USDT.usd,1001);
  assert.equal(r.components.breadth.denominator,12);
  assert.equal(r.components.breadth.coverage,12);
});
test('missing universe member fails breadth without concealing stablecoin coverage',()=>{
  const r=contextSnapshot(rows().filter(x=>x.id!=='near'),now);
  assert.equal(r.components.breadth.status,'unavailable');
  assert.equal(r.components.stablecoin_caps.status,'available');
});
test('stale, unsynchronised or invalid observations are not accepted',()=>{
  for(const mutate of [r=>r.find(x=>x.id==='ethereum').last_updated='2026-10-15T04:00:00Z',r=>r.find(x=>x.id==='ethereum').current_price=NaN,r=>r.find(x=>x.id==='ethereum').last_updated='2026-10-15T07:00:00Z']){
    const p=rows();mutate(p);assert.equal(contextSnapshot(p,now).components.eth_btc.status,'unavailable');
  }
});
