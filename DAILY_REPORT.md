# SS CRYPTO daily reporting integration

The daily report now combines the existing BTC/USDT closed-candle dataset and the CoinGecko dominance collector. Existing BTC collector files and schedules are unchanged.

## Run

Python 3.12+, `reportlab` and `tzdata` are needed for PDF output. On Linux install `fonts-dejavu-core` if not available; Windows uses Arial.

```text
python ss_crypto_daily_report.py --fetch --input-dir report-input --output-dir reports --pdf
```

The fetch mode resolves one GitHub commit and downloads BTC, dominance and monthly history from that immutable commit. It writes the commit into the report model and source links. It never changes collector data. JSON and Markdown always render; PDF requires `--pdf`.

For the requested test add `--test-report`. The dated outputs then end in `_teszt`; regular daily reports are not marked as test reports.

## Daily content

- BTC: 4H, 1D, 1W; at least 200 closed candles per timeframe; EMA20/50/200, RSI14, MACD and ATR14. Each timeframe has its actual candle closing time. No live spot price is invented.
- Dominance: BTC.D, ETH.D, USDT.D, USDC.D, TOTAL, TOTAL2, TOTAL3. Percent and USD units are explicit. CoinGecko snapshots are not direct TradingView CRYPTOCAP OHLC candles.
- Around-24h change: dominance differences in percentage points; capitalization differences in percent. Baseline must be within 90 minutes of the target timestamp. Actual baseline and elapsed interval are stated. Missing reference means unavailable, never zero.
- More-than-two-hour source data are marked stale. One initial sample is not a trend or evidence of rotation. Source timing differs between BTC and global market data.
- Invalid, missing or inconsistent values fail the report rather than producing fabricated output. A short history does not prevent a clearly marked initial report.

## Verification

The local fixture-based verification covers real inputs, missing or inconsistent values, percentage versus percentage-point changes and flat-market indicator edge cases. The test report from 2026-10-15 is based on actual recorded data; synthetic data are used only for indicator and comparison unit tests. PDF export is reopened, its text checked and all pages visually inspected before delivery.

This integration is a reusable report generator. It does not change any pre-existing ChatGPT scheduled task or set a new report delivery time.

GitHub Actions: `SS CRYPTO daily report` is a manual workflow and runs once when its code is deployed to main. Its test generates PDF, Markdown and a JSON model from the checked-out collector outputs, verifies the PDF and uploads all results as an artifact for 30 days. It uses read-only repository permissions and does not modify data collectors.
