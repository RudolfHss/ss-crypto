# SS CRYPTO CoinGecko dominance collector

Separate from the existing BTC OHLCV collector; no existing BTC files or workflow are modified.

Runs hourly at minute 17 UTC, manually from Actions, and once when collector code is deployed to main. GitHub schedules can be delayed or skipped; this is not a real-time feed or a guaranteed hourly candle series.

Source: [CoinGecko /global](https://docs.coingecko.com/demo/reference/crypto-global), a single global market snapshot per run. BTC.D, ETH.D, USDT.D and USDC.D are CoinGecko market_cap_percentage values in percent. TOTAL is total_market_cap.usd. TOTAL2 = TOTAL × (1 − BTC.D / 100); TOTAL3 = TOTAL × (1 − (BTC.D + ETH.D) / 100). These cover CoinGecko's asset universe and are **not direct TradingView CRYPTOCAP candles**, OHLC, or TradingView-equivalent index values.

`ss_crypto_dominance_latest.json` holds the latest valid sample. `data/dominance/YYYY-MM.json` holds timestamped monthly JSON arrays, retained indefinitely in the repository. Both `observed_at` (actual collection UTC) and `source_updated_at` (provider UTC) are recorded. History begins at deployment; no fabricated backfill or missing-hour interpolation. Repeated source timestamps are ignored. Source timestamps more than two hours old, invalid/missing metrics and corrupted history fail without replacing valid output.

Uses Node.js 22 built-ins, no third-party dependencies. Tests: `node --test tests/dominance.test.mjs`. Collect: `node ss_crypto_dominance.mjs`.

The public endpoint is tried without a key when no secret is set. If CoinGecko requires authentication, set a **Demo** API key only under repository Settings → Secrets and variables → Actions → New repository secret, named `COINGECKO_DEMO_API_KEY`. Never paste keys into chat, source files, JSON, or workflow input. The key is sent only in the CoinGecko request header. Pro keys are not supported by this Demo endpoint. Authentication failures include instructions; temporary failures retry with bounded delays.

The workflow needs `contents: write` to commit only the dominance JSON files. It rebases to accommodate BTC collector commits without editing BTC files. Each successful collection is also uploaded as an Actions artifact for 30 days. Confirm a green run, seven metrics, fresh source timestamp and a new JSON commit. A failing API call does not manufacture data.
