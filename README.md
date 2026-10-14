# SS CRYPTO market data collector

Runs every 30 minutes on GitHub Actions and manually with **Actions > SS CRYPTO BTC data > Run workflow**. Tries Coinbase, OKX, Bybit for 200 closed BTC/USDT spot OHLCV candles on 4H/1D/1W, validates and writes `ss_crypto_btc_ohlcv.json` into the repository.

Coinbase uses the public Exchange API for BTC-USDT, without API keys. Four-hour candles are aggregated from four hourly candles; weekly candles from seven daily candles, starting Monday at 00:00 UTC. Requests are paginated below the 300-candle API limit. Missing constituent candles reject the source rather than producing incomplete aggregates. All three timeframes in each output come from the same exchange.

## Setup
1. Create a GitHub repository and upload `ss_crypto_market_data.py` and `.github/workflows/market-data.yml` preserving paths.
2. Enable Actions and workflow write permissions under Settings > Actions > General > Workflow permissions.
3. Run workflow manually; verify green run, artifact and generated JSON.
4. For public repository, JSON can be read via `https://raw.githubusercontent.com/OWNER/REPO/main/ss_crypto_btc_ohlcv.json` (replace OWNER/REPO and branch). Public repositories expose data to everyone.

**Caution:** GitHub scheduled workflows can run late or be skipped, so not suitable for minute-scale scalping or real-time trading. ChatGPT automations cannot automatically ingest this file without a separately configured integration and tested access. No exchange API keys are needed. No trades are executed.
