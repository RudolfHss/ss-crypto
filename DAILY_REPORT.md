# SS CRYPTO napi jelentés - auditált működés

A napi lánc: friss BTC-adatgyűjtés és CoinGecko-lekérés -> minőségellenőrzés -> közös jelentésmodell -> PDF, Markdown és JSON -> tartalmi ellenőrzés -> GitHubon elérhető eredmény. Nincs kereskedés vagy élő scalp/perpetual figyelő.

## Időzítés és elérhetőség

Jóváhagyott reggeli idő: **07:30 Europe/Budapest**. A két UTC cron (05:30 és 06:30) közül a téli/nyári helyi idő alapján csak a megfelelő fut. A késleltetve induló helyes futás is elfogadott; az aznapi már meglévő rendes jelentés ismétlését a kapu tiltja. A GitHub Actions késhet vagy ütemezett futást kihagyhat, így pontos érkezés nem garantált. Ez nem tőzsdenyitásra optimalizált időpont.

Kézbesítés: **GitHub és innen megnyitható eredmény**, a felhasználó választása szerint. A rendes jelentések a `reports/YYYY-MM-DD/` alatt PDF/Markdown/JSON formában, dátumozva kerülnek a tárolóba. `reports/README.md` a legutóbbi eredményre mutat, `reports/latest.json` a következő jelentés előzőjelentés-referenciája. A GitHub Actions mentése az adatokat is tartalmazza, 90 napig. A rendes jelentések a tároló Git-előzményeivel megmaradnak. Ismeretlen ChatGPT-automatizmus nem módosult.

Kézi futtatás: Actions -> SS CRYPTO daily report -> Run workflow. Az alapértelmezett tesztfutás nem írja felül a rendes napi baseline-t. A rendes futás a tesztjelölő kikapcsolásával indítható a main ágon. Push esetén az ellenőrzések és valódi adatos tesztjelentés fut; pull request esetén csak a determinisztikus, titok nélküli tesztek. Fork PR nem kap gyűjtői secretet.

## Adatkapu

- Állapotok: **friss / korlátozott / nem értékelhető**. A legrosszabb modulállapot adja a jelentés állapotát. Hibás vagy hiányzó BTC/dominancia alapadat nem értékelhető. Hiányzó kiegészítő modul korlátozott. Korlátozott/nem értékelhető összállapotban az elemzés történeti; az aktuális forgatókönyv-aktiválás tiltva. Új trade jelzés a napi rendszerben egyáltalán nem készül.
- BTC lekérési frissesség: legfeljebb 90 perc friss; 90 perc felett, 24 óráig korlátozott; 24 óra felett nem értékelhető.
- CoinGecko forrás- és lekérési frissesség: legfeljebb 120 perc friss; 120 perc felett, 24 óráig korlátozott; utána nem értékelhető. Az 5 percnél távolabbi jövőbeli időbélyeg hibás.
- A lekérés idejét és a gyertya utolsó elvárt lezárását **külön** ellenőrizzük minden idősíkon. Az elvárt zárás `floor_UTC(értékelési idő - 5 perc)`: 4H UTC 00/04/08/12/16/20; napi UTC 00:00; heti UTC hétfő 00:00. A szolgáltatói lezárásnak 5 perc türelmi idő jár; a még nyitott nap/hét nem hiányzó adat.
- Igazítás, minden belső hézag (heti is), időbélyeg, véges OHLCV, ársorrend és lezártság ellenőrzött. Hiányzó gyertya nincs interpolálva. Sikertelen mostani gyűjtésnél a megmaradt régi adat sem kap friss ajánlási jogosultságot.

## BTC és technikai módszerek

Egy teljes gyűjtés mindhárom idősíkja ugyanarról a tőzsdéről származik. Sorrend: Coinbase, OKX, Bybit. A Coinbase 4H órás, heti napi teljes alkotógyertyákból aggregált. Az OKX történeti végpontja **1Dutc/1Wutc** paramétert használ, paginálva. A Bybit eredményét is az UTC-határokhoz mérjük; eltérő igazítás vagy hiány elutasítja a forrást. Forrásváltás látszik a jelentésben; tőzsdék volumene nem keverhető, az előző jelentés árszintváltozása ilyenkor nincs közvetlenül összehasonlítva.

Kért előzmény: 1000 lezárt 4H és napos, legfeljebb 600 heti gyertya. Rövidebb heti BTC/USDT-listázási történet esetén legalább 200 teljes, folytonos heti gyertya kell. Az EMA200 **csak legalább 1000 gyertyával** közölt; a heti mutató ezért hiányozhat. A korai hiányzó heti prefix megengedett, a soron belüli vagy friss végi hiány nem.

EMA-inicializálás: a rendelkezésre álló első záróár; EMA200-nál 1000 minta után az induló érték súlya `(199/201)^999`, körülbelül 0,0046%. Független, 50 jegyű Decimal zárt alakú referencia ellenőrzi a rekurziót. RSI14/ATR14: Wilder. MACD: 12/26/9. Az indikátorokat nem adjuk össze független bizonyítékokat feltételező pontszámmá.

Szerkezet: szigorú 2 bal/2 jobb gyertyás lokális szélsőértékek; csak a jobb oldali gyertyák zárása után megerősítettek. Utolsó két megerősített csúcs és mélypont együtt HH/HL -> emelkedő, LH/LL -> eső; más sorrend vegyes/sávos; kevés pivot esetén nem eldönthető. Az EMA-sorrend külön leírás, nem szerkezet. A riport minden pivot megerősítési időpontját megtartja.

Heti háttér -> napos trend/kulcsszintek -> 4H megerősítés. RVOL20: az utolsó gyertya alapvolumene / a megelőző 20 gyertya átlaga; az aktuális gyertya nincs a nevezőben. Megerősítési küszöb 1,20. Feltételes emelkedő/eső/sávos forgatókönyvekhez megerősítés és érvénytelenítés szerepel. A sáv a két utolsó 4H megerősítő gyertya előtti 20 gyertya széle; nincs jövőbeli adat vagy kitalált valószínűség. A küszöb nem hozamígéret.

## Dominancia és tényleges kiegészítő adatok

CoinGecko `/global`: négy százalékos részesedés és három kapitalizációs mutató. TOTAL2 és TOTAL3 algebrailag származtatott; nem hét független jel, nem TradingView CRYPTOCAP-gyertyák és nem azonos indexek. Dominanciaváltozás százalékpontban, kapitalizációváltozás százalékban. Kb. 24h referencia legfeljebb 90 perccel térhet el a célidőtől; a tényleges időköz szerepel. Referenciahiány nem nulla és nem kitalált trend.

CoinGecko `/coins/markets` valódi megfigyeléseiből:

- ETH/BTC: ETH USD-ár / BTC USD-ár; gördülő 24h relatív hozam `(1+r_ETH)/(1+r_BTC)-1`. Ez keresztárfolyam, nem tőzsdei ETH/BTC-gyertya. A két forrásidő legfeljebb 10 percet térhet el.
- USDT és USDC abszolút kapitalizáció: a tényleges USD `market_cap` mező, nem a globális dominanciából becsülve.
- Rögzített, egyenlő darabszámú 12-token részvétel: ethereum, solana, binancecoin, ripple, dogecoin, cardano, chainlink, avalanche-2, polkadot, uniswap, litecoin, near. Mutató: a pozitív gördülő 24h USD-hozamú tagok aránya. Teljes 12/12 lefedettség és legfeljebb 10 perc forrásidő-eltérés kell; egy hiányzó tag esetén a részvétel hiányzik, a nevezőt nem csökkentjük. Nem teljes altcoinpiaci lefedettség és nem TOTAL3-átnevezés.

Univerzumverzió `fixed-v1-2026-10-15`; a megfigyelés ettől a naptól épül a `data/context/` alatt. Nincs visszamenőleges adat vagy korábbi univerzum rekonstruálva. API-hiány esetén a modul a konkrét hiányt közli. A dominancia, a keresztárfolyam és a stabilcoin-kapitalizáció önmagában nem bizonyít tőkeáramlást.

## Futtatás és ellenőrzés

Python 3.12, Node 22, `python -m pip install -r requirements-report.txt`. Windows Arial, Linux DejaVu Sans kell a PDF-hez.

```text
python -m unittest -v test_ss_crypto.py
node --test test_context.mjs tests/dominance.test.mjs
python ss_crypto_pipeline.py --test-report
```

A PDF, Markdown és JSON ugyanabból a dokumentummodellből készül. Tartalomhash és minden szöveg/táblázat ellenőrzött a visszaolvasott PDF-ben és Markdownban; a teszt nem oldalszámot tekint tartalmi bizonyítéknak. A valódi tesztjelentés vizuális PDF-ellenőrzést is kap. A szintetikus tesztfixture nem jelenik meg valódi piaci jelentésként.

Ismert korlátok: nincs élő spot ticker, rövid idősíkú vagy perpetual adatfolyam, automatikus kereskedés, kéretlen scalp-riasztás. Ezekhez konkrét piacok és külön jóváhagyott adatfolyam-terv kellene. A napi jelentésben csak lezárt 4H/1D/1W spotadatot értékelünk.

Forrásdokumentáció: [Coinbase gyertyák](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles), [OKX market data](https://www.okx.com/docs-v5/en/#rest-api-market-data), [CoinGecko /global](https://docs.coingecko.com/demo/reference/crypto-global), [CoinGecko /coins/markets](https://docs.coingecko.com/demo/reference/coins-markets).
