# CoinGecko dominancia és kiegészítő környezet

A gyűjtő óránként, a 17. percre ütemezve fut; kézzel is indítható. A GitHub-ütemezés késhet. Új adatok a gyűjtés indulásától épülnek, visszamenőleges adatok nincsenek kitalálva.

`ss_crypto_dominance_latest.json` és `data/dominance/YYYY-MM.json`: BTC.D, ETH.D, USDT.D, USDC.D százalékban; TOTAL USD-ben; TOTAL2 = TOTAL × (1 - BTC.D/100), TOTAL3 = TOTAL × (1 - (BTC.D + ETH.D)/100). A hét érték nem hét független jel. Ezek CoinGecko-pillanatképek, **nem közvetlen TradingView CRYPTOCAP-gyertyák vagy azonos indexek**. A dominancia önmagában nem tőkeáramlás.

`ss_crypto_context.json` és `data/context/YYYY-MM.json`: a valódi `/coins/markets` válaszból származtatott ETH/BTC-keresztárfolyam és gördülő 24h relatív erő; USDT/USDC tényleges abszolút `market_cap` USD mezők; rögzített 12-token pozitív 24h hozamrészvétel. A teljes univerzum, verzió és tagonkénti megfigyelés a JSON-ban szerepel. Egy hiányzó vagy elavult tagnál a részvétel nem elérhető, a nevező nem csökken. Nem a TOTAL3 átnevezése és nem történeti univerzumrekonstrukció.

API-hiba esetén a globális dominancia gyűjtése hibás futással végződik; a korábbi valid JSON nem lesz hamis adatra cserélve. A kiegészítő környezet komponensenként jelzi az adat hiányát. A napi jelentés önálló minőségellenőrzést végez, és elavult/hiányos adatból aktuális jelzést nem ad.

Node 22 beépített modulok, külső függőség nélkül. Kulcs csak `COINGECKO_DEMO_API_KEY` GitHub Actions Secretként adható meg, soha chatben vagy forrásban. A kulcs a CoinGecko kérés fejlécébe kerül. A nyilvános kulcs nélküli lekérés működése esetén nem kell secret.

Teljes módszertan, rögzített univerzum, küszöbök és tesztelés: [DAILY_REPORT.md](DAILY_REPORT.md).
