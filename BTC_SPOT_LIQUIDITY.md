# BTC spot order-book liquidity

Public, keyless BTC/USDT snapshots from Bitget spot (200 levels per side) and OKX spot (400). Exchanges remain separate; quantities are BTC and notionals are USDT. No account access or order submission. Bitget replaces Bybit because Bybit returned HTTP 403 from the GitHub hosted runner. The active exchange keys are now `bitget` and `okx`; consumers must use these keys rather than expecting `bybit`. Bitget's fixed request explicitly sets `category=SPOT` and `symbol=BTCUSDT`; its response does not echo the symbol.

Run `python btc_spot_liquidity.py`, then `python btc_spot_liquidity.py --check`. Output: `data/btc_spot_liquidity.json`. Consumers must run the check immediately before use: both file and exchange timestamps must be at most 45 minutes old, with at most five seconds future clock tolerance. Receipt checks reject exchange data older than 60 seconds. Live workflow verification uses a stricter 120-second gate. A new file timestamp cannot make an old source fresh.

`fresh` means both exchanges passed; `limited` means one passed and the other has an explicit error; `unavailable` means neither passed and the command fails. Errors are retried three times with bounded timeouts. All-source failures replace local old success with an unavailable snapshot and fail CI. A failed workflow does not publish: the previous repository snapshot ages and must be rejected by consumers. Always inspect each exchange status.

Raw depth, spread, largest visible levels by notional, and cumulative depth within 10/25/50/100 bps of each exchange midpoint are included. Each band has separate bid/ask coverage flags: when false, the notional is only a lower bound within the returned depth. Never infer absent liquidity beyond capped depth. Displaying a book later requires rechecking its source timestamp.

These are sampled visible resting orders, not a liquidation heatmap. Hidden/RPI orders may be excluded; orders can be cancelled or spoofed. Largest levels are observations, not persistent support/resistance or trade signals. No historical persistence is inferred. Different exchanges and collection times must not be merged into a single executable book.

Workflow: tests + real public API collection + independent freshness check + downloadable artifact on PR/feature pushes. Main-only publishing starts after merge, every 30 minutes at UTC minutes 7/37, or manually. GitHub schedules can be delayed: this is not a real-time feed. The existing daily report and 08:00 Europe/Budapest ChatGPT automation are unchanged. No ALT/SCALP watcher is started.

Tests: `python -m unittest -v test_btc_spot_liquidity.py`.

Sources: [Bitget orderbook](https://www.bitget.com/docs/catalog/market/market-data), [OKX market data](https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-order-book).
