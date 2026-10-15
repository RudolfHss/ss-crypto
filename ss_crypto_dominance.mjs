import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ENDPOINT = 'https://api.coingecko.com/api/v3/global';
export const ALT_UNIVERSE = ['ethereum','solana','binancecoin','ripple','dogecoin','cardano','chainlink','avalanche-2','polkadot','uniswap','litecoin','near'];
export const UNIVERSE_VERSION = 'fixed-v1-2026-10-15';
const CONTEXT_IDS = [...new Set(['bitcoin','tether','usd-coin',...ALT_UNIVERSE])];
export function snapshot(payload, now = new Date()) {
  const d = payload?.data;
  const total = d?.total_market_cap?.usd;
  if (!Number.isFinite(total) || total <= 0) throw new Error('Invalid USD total market cap');
  const values = {};
  for (const coin of ['btc', 'eth', 'usdt', 'usdc']) {
    const p = d?.market_cap_percentage?.[coin];
    if (!Number.isFinite(p) || p <= 0 || p >= 100) throw new Error(`Invalid dominance: ${coin}`);
    values[`${coin.toUpperCase()}.D`] = p;
  }
  if (Object.values(values).reduce((a, b) => a + b, 0) > 100) throw new Error('Dominance sum exceeds 100');
  const ts = d?.updated_at;
  if (!Number.isInteger(ts) || ts <= 0 || now.getTime() / 1000 - ts > 7200 || ts - now.getTime() / 1000 > 300) {
    throw new Error('Missing, stale or future source timestamp');
  }
  values.TOTAL = total;
  values.TOTAL2 = total * (1 - values['BTC.D'] / 100);
  values.TOTAL3 = total * (1 - (values['BTC.D'] + values['ETH.D']) / 100);
  return {
    schema_version: 1,
    source: 'CoinGecko /global',
    endpoint: ENDPOINT,
    methodology: 'CoinGecko snapshot; dominance in percent; TOTAL in USD; TOTAL2 excludes BTC; TOTAL3 excludes BTC and ETH. Not TradingView CRYPTOCAP OHLC candles.',
    observed_at: now.toISOString(),
    source_updated_at: new Date(ts * 1000).toISOString(),
    values,
  };
}

async function readJSON(path, fallback) {
  try { return JSON.parse(await readFile(path, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}

async function atomicJSON(path, value) {
  await mkdir(dirname(path), { recursive: true });
  const temp = `${path}.tmp`;
  await writeFile(temp, JSON.stringify(value, null, 2) + '\n');
  await rename(temp, path);
}

export async function persist(sample, root = '.') {
  const month = sample.source_updated_at.slice(0, 7);
  const historyPath = join(root, 'data/dominance', `${month}.json`);
  const latestPath = join(root, 'ss_crypto_dominance_latest.json');
  const history = await readJSON(historyPath, []);
  if (!Array.isArray(history) || history.some(row => row.schema_version !== 1 || !row.source_updated_at || !row.values)) {
    throw new Error('Invalid history; refusing to overwrite');
  }
  const latest = await readJSON(latestPath, null);
  if (latest && sample.source_updated_at < latest.source_updated_at) throw new Error('Source timestamp regressed');
  const existing = history.find(row => row.source_updated_at === sample.source_updated_at);
  if (existing) {
    if (JSON.stringify(existing.values)!==JSON.stringify(sample.values)) throw new Error('Conflicting values for existing source timestamp');
    if (!latest || latest.source_updated_at < existing.source_updated_at) await atomicJSON(latestPath,existing);
    return false;
  }
  history.push(sample);
  history.sort((a, b) => a.source_updated_at.localeCompare(b.source_updated_at));
  await atomicJSON(historyPath, history);
  await atomicJSON(latestPath, sample);
  return true;
}

export function contextSnapshot(payload, now = new Date()) {
  if (!Array.isArray(payload)) throw new Error('Invalid CoinGecko markets payload');
  const byId = new Map();
  for (const row of payload) {
    if (byId.has(row.id)) throw new Error('Duplicate CoinGecko coin ID');
    byId.set(row.id,row);
  }
  const requireRow = id => {
    const row = byId.get(id);
    const ts = Date.parse(row?.last_updated);
    if (!row || !Number.isFinite(ts) || now.getTime()-ts > 7200000 || ts-now.getTime()>300000) throw new Error(`Missing/stale markets row: ${id}`);
    return row;
  };
  const result = {schema_version:1,source:'CoinGecko /coins/markets',observed_at:now.toISOString(),universe_version:UNIVERSE_VERSION,universe:ALT_UNIVERSE,universe_started_at:'2026-10-15',methodology:'Forward fixed-universe equal-count breadth: positive rolling-24h USD return; full 12/12 coverage required. Not historical universe reconstruction, fund flows, or a TOTAL3 alias.',components:{}};
  for (const name of ['stablecoin_caps','eth_btc','breadth']) {
    try {
      if (name==='stablecoin_caps') {
        const values = {};
        for (const [symbol,id] of [['USDT','tether'],['USDC','usd-coin']]) {
          const row=requireRow(id);
          if (!Number.isFinite(row.market_cap)||row.market_cap<=0) throw new Error(`Invalid absolute cap: ${id}`);
          values[symbol]={usd:row.market_cap,source_updated_at:row.last_updated};
        }
        result.components[name]={status:'available',values,method:'Actual market_cap USD fields; not inferred from global dominance'};
      } else if (name==='eth_btc') {
        const btc=requireRow('bitcoin'),eth=requireRow('ethereum');
        for (const row of [btc,eth]) if (!Number.isFinite(row.current_price)||row.current_price<=0||!Number.isFinite(row.price_change_percentage_24h)||row.price_change_percentage_24h<=-100) throw new Error('Invalid ETH/BTC inputs');
        if (Math.abs(Date.parse(btc.last_updated)-Date.parse(eth.last_updated))>600000) throw new Error('ETH/BTC source times differ by >10 minutes');
        result.components[name]={status:'available',ratio:eth.current_price/btc.current_price,relative_change_24h_pct:((1+eth.price_change_percentage_24h/100)/(1+btc.price_change_percentage_24h/100)-1)*100,source_updated_at:[btc.last_updated,eth.last_updated].sort()[0],method:'ETH USD quote / BTC USD quote; relative rolling-24h return from same API batch; derived cross-rate, not an exchange ETH/BTC candle'};
      } else {
        const observations=ALT_UNIVERSE.map(id=>{
          const row=requireRow(id);
          if (!Number.isFinite(row.price_change_percentage_24h)) throw new Error(`Missing 24h return: ${id}`);
          return {id,return_24h_pct:row.price_change_percentage_24h,source_updated_at:row.last_updated};
        });
        if (Math.max(...observations.map(r=>Date.parse(r.source_updated_at)))-Math.min(...observations.map(r=>Date.parse(r.source_updated_at)))>600000) throw new Error('Breadth source times differ by >10 minutes');
        const advancing=observations.filter(r=>r.return_24h_pct>0).length;
        result.components[name]={status:'available',advancing,denominator:ALT_UNIVERSE.length,positive_pct:advancing/ALT_UNIVERSE.length*100,coverage:observations.length,observations,source_updated_at:observations.map(r=>r.source_updated_at).sort()[0]};
      }
    } catch (error) { result.components[name]={status:'unavailable',reason:error.message}; }
  }
  return result;
}

export async function fetchGlobal(endpoint = ENDPOINT) {
  const headers = { accept: 'application/json', 'user-agent': 'SS-CRYPTO-dominance/1.0' };
  if (process.env.COINGECKO_DEMO_API_KEY) headers['x-cg-demo-api-key'] = process.env.COINGECKO_DEMO_API_KEY;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const res = await fetch(endpoint, { headers, signal: AbortSignal.timeout(30000) });
      if (!res.ok) {
        const error = new Error(`CoinGecko HTTP ${res.status}${[401, 403].includes(res.status) ? ': configure COINGECKO_DEMO_API_KEY in GitHub Actions secrets' : ''}`);
        error.permanent = res.status !== 429 && res.status < 500;
        throw error;
      }
      return await res.json();
    } catch (error) {
      if (error.permanent || attempt === 3) throw error;
      await new Promise(r => setTimeout(r, 10000 * (attempt + 1)));
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  let failed = false;
  try {
    const sample = snapshot(await fetchGlobal());
    const added = await persist(sample);
    console.log(JSON.stringify({ added, source_updated_at: sample.source_updated_at, values: sample.values }));
  } catch (error) {
    console.error(error.message);
    failed = true;
  }
  let context;
  try {
    const query = new URLSearchParams({vs_currency:'usd',ids:CONTEXT_IDS.join(','),per_page:'50',page:'1',sparkline:'false'});
    context = contextSnapshot(await fetchGlobal('https://api.coingecko.com/api/v3/coins/markets?'+query));
  } catch (error) {
    context = {schema_version:1,source:'CoinGecko /coins/markets',observed_at:new Date().toISOString(),universe_version:UNIVERSE_VERSION,universe:ALT_UNIVERSE,components:Object.fromEntries(['stablecoin_caps','eth_btc','breadth'].map(k=>[k,{status:'unavailable',reason:error.message}]))};
  }
  await atomicJSON('ss_crypto_context.json',context);
  const historyPath = join('data/context',context.observed_at.slice(0,7)+'.json');
  const history = await readJSON(historyPath,[]);
  if (!Array.isArray(history)) throw new Error('Invalid context history');
  history.push(context);
  await atomicJSON(historyPath,history);
  console.log(JSON.stringify({context:Object.fromEntries(Object.entries(context.components).map(([k,v])=>[k,v.status]))}));
  if (failed) process.exitCode=1;
}
