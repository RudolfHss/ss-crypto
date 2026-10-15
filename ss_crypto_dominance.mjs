import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ENDPOINT = 'https://api.coingecko.com/api/v3/global';
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
  if (history.some(row => row.source_updated_at === sample.source_updated_at)) return false;
  history.push(sample);
  history.sort((a, b) => a.source_updated_at.localeCompare(b.source_updated_at));
  await atomicJSON(historyPath, history);
  await atomicJSON(latestPath, sample);
  return true;
}

export async function fetchGlobal() {
  const headers = { accept: 'application/json', 'user-agent': 'SS-CRYPTO-dominance/1.0' };
  if (process.env.COINGECKO_DEMO_API_KEY) headers['x-cg-demo-api-key'] = process.env.COINGECKO_DEMO_API_KEY;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const res = await fetch(ENDPOINT, { headers, signal: AbortSignal.timeout(30000) });
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
  try {
    const sample = snapshot(await fetchGlobal());
    const added = await persist(sample);
    console.log(JSON.stringify({ added, source_updated_at: sample.source_updated_at, values: sample.values }));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
