# SS CRYPTO

BTC/USDT spotadatok, CoinGecko dominancia és auditált napi jelentés. Nincs automatikus kereskedés vagy élő scalp/perpetual jelzés.

- BTC: félóránként; elsődlegesen Coinbase, tartalékként OKX/Bybit. Mindhárom idősík ugyanarról a forrásról. UTC-igazítás, teljes heti folytonosság és lezártság ellenőrzött. A 4H és napos előzmény 1000 gyertya; a heti elérhető listázási történettől függ. Rövid bemelegítésből EMA200 nem jelenik meg.
- CoinGecko: óránként, négy dominancia és TOTAL/TOTAL2/TOTAL3, időbélyegzett havi JSON-előzménnyel. Nem közvetlen TradingView CRYPTOCAP-adat. Valódi API-adatokból külön ETH/BTC-relatív erő, stabilcoin-abszolút kapitalizáció és rögzített 12-token részvétel; hiányos lefedettség látható hiány marad.
- Napi lánc: **07:30 Europe/Budapest**, téli/nyári időváltással; friss gyűjtés -> minőségkapu -> PDF/Markdown/JSON -> ellenőrzés -> GitHub. Késések lehetségesek.

[Legutóbbi rendes napi jelentés](reports/README.md) · [Részletes módszertan és korlátok](DAILY_REPORT.md) · [Napi workflow](https://github.com/RudolfHss/ss-crypto/actions/workflows/daily-report.yml)

Az adatállapot friss, korlátozott vagy nem értékelhető. Hibás/elavult adatból nem keletkezik aktuális ajánlás vagy új trade jelzés. A korábbi ChatGPT-automatizmust ez a projekt nem módosítja.

API-kulcs csak a `COINGECKO_DEMO_API_KEY` GitHub Actions Secretben tárolható. Ha a nyilvános API kulcs nélkül működik, nem kell secret. Kulcsot ne írj chatbe vagy forráskódba.
