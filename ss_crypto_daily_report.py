"""SS CRYPTO daily report: read-only BTC and CoinGecko integration."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
BASE = 'https://raw.githubusercontent.com/RudolfHss/ss-crypto/'
TF = {'4H': 14400, '1D': 86400, '1W': 604800}
KEYS = ['BTC.D', 'ETH.D', 'USDT.D', 'USDC.D', 'TOTAL', 'TOTAL2', 'TOTAL3']

def stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'SS-CRYPTO-daily-report/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def fetch_inputs(folder):
    folder.mkdir(parents=True, exist_ok=True)
    commit = get_json('https://api.github.com/repos/RudolfHss/ss-crypto/commits/main')['sha']
    for name in ['ss_crypto_btc_ohlcv.json', 'ss_crypto_dominance_latest.json']:
        value = get_json(BASE + commit + '/' + name)
        (folder / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    latest = json.loads((folder / 'ss_crypto_dominance_latest.json').read_text(encoding='utf-8'))
    end = stamp(latest['source_updated_at'])
    previous = end.replace(day=1) - dt.timedelta(days=1)
    for month in sorted({end.strftime('%Y-%m'), previous.strftime('%Y-%m')}):
        name = 'data/dominance/' + month + '.json'
        try:
            value = get_json(BASE + commit + '/' + name)
        except urllib.error.HTTPError as error:
            if error.code != 404: raise
            value = []
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2), encoding='utf-8')
    (folder / 'provenance.json').write_text(json.dumps({'commit': commit}), encoding='utf-8')

def ema(values, length):
    result = [values[0]]
    for value in values[1:]: result.append(result[-1] + 2 / (length + 1) * (value - result[-1]))
    return result

def metrics(rows):
    close = [r['close'] for r in rows]
    changes = [b - a for a, b in zip(close, close[1:])]
    gains = sum(max(x, 0) for x in changes[:14]) / 14
    losses = sum(max(-x, 0) for x in changes[:14]) / 14
    tr = [max(r['high'] - r['low'], abs(r['high'] - close[i-1]), abs(r['low'] - close[i-1])) for i, r in enumerate(rows) if i]
    atr = sum(tr[:14]) / 14
    for x in changes[14:]: gains = (gains * 13 + max(x, 0)) / 14; losses = (losses * 13 + max(-x, 0)) / 14
    for x in tr[14:]: atr = (atr * 13 + x) / 14
    rsi = 50 if gains == losses == 0 else (100 if losses == 0 else 100 - 100 / (1 + gains / losses))
    macd = [a-b for a, b in zip(ema(close, 12), ema(close, 26))]
    signal = ema(macd, 9)[-1]
    return {'close': close[-1], 'ema20': ema(close, 20)[-1], 'ema50': ema(close, 50)[-1], 'ema200': ema(close, 200)[-1], 'rsi14': rsi, 'atr14': atr, 'macd': macd[-1], 'macd_signal': signal, 'macd_hist': macd[-1] - signal, 'change_pct': (close[-1] / close[-2] - 1) * 100, 'open_time_utc': rows[-1]['open_time_utc']}

def validate_sample(sample):
    if sample.get('schema_version') != 1 or sample.get('source') != 'CoinGecko /global': raise ValueError('Unknown dominance source or schema')
    stamp(sample['source_updated_at']); stamp(sample['observed_at'])
    v = sample['values']
    if set(v) != set(KEYS) or any(not isinstance(v[k], (int, float)) or isinstance(v[k], bool) or not math.isfinite(v[k]) or v[k] <= 0 for k in KEYS): raise ValueError('Missing or invalid dominance metrics')
    if any(v[k] >= 100 for k in KEYS[:4]) or sum(v[k] for k in KEYS[:4]) > 100: raise ValueError('Invalid dominance percentages')
    for k, expected in [('TOTAL2', v['TOTAL'] * (1-v['BTC.D']/100)), ('TOTAL3', v['TOTAL'] * (1-(v['BTC.D']+v['ETH.D'])/100))]:
        if not math.isclose(v[k], expected, rel_tol=1e-9): raise ValueError('Inconsistent ' + k)

def compare(latest, history, hours):
    target = stamp(latest['source_updated_at']) - dt.timedelta(hours=hours)
    candidates = [r for r in history if stamp(r['source_updated_at']) < stamp(latest['source_updated_at']) and abs((stamp(r['source_updated_at']) - target).total_seconds()) <= 5400]
    if not candidates: return None
    before = min(candidates, key=lambda r: abs((stamp(r['source_updated_at']) - target).total_seconds()))
    return {'baseline_at': before['source_updated_at'], 'interval_hours': (stamp(latest['source_updated_at']) - stamp(before['source_updated_at'])).total_seconds()/3600, 'changes': {k: latest['values'][k] - before['values'][k] if k.endswith('.D') else (latest['values'][k]/before['values'][k]-1)*100 for k in KEYS}}

def build_model(folder, now=None):
    now = now or dt.datetime.now(UTC)
    btc = json.loads((folder / 'ss_crypto_btc_ohlcv.json').read_text(encoding='utf-8-sig'))
    latest = json.loads((folder / 'ss_crypto_dominance_latest.json').read_text(encoding='utf-8-sig'))
    validate_sample(latest)
    history = []
    for path in sorted((folder / 'data/dominance').glob('*.json')):
        rows = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(rows, list): raise ValueError('Invalid history')
        for row in rows: validate_sample(row)
        history.extend(rows)
    if not any(r == latest for r in history): raise ValueError('Latest dominance sample missing from history')
    if btc.get('status') != 'ok' or btc.get('market') != 'BTC/USDT': raise ValueError('Invalid BTC dataset')
    age_btc = (now - stamp(btc['retrieved_at_utc'])).total_seconds()/60
    age_dom = (now - stamp(latest['source_updated_at'])).total_seconds()/60
    if min(age_btc, age_dom) < -5: raise ValueError('Future dataset')
    warnings = []
    if age_btc > 120: warnings.append('A BTC-adatfelvétel több mint 2 órás; az árfolyamadat nem élő.')
    if age_dom > 120: warnings.append('A dominanciaforrás több mint 2 órás; friss piaci következtetéshez új adat kell.')
    result = {}
    for tf, seconds in TF.items():
        rows = btc['timeframes'][tf]
        if len(rows) < 200: raise ValueError('Insufficient candles: ' + tf)
        previous = None
        for row in rows:
            start = stamp(row['open_time_utc'])
            if start + dt.timedelta(seconds=seconds) > stamp(btc['retrieved_at_utc']): raise ValueError('Open candle in ' + tf)
            if previous and (start - previous).total_seconds() != seconds: raise ValueError('Candle gap in ' + tf)
            previous = start
            if any(not isinstance(row[k], (int, float)) or not math.isfinite(row[k]) for k in ['open','high','low','close','volume_base']): raise ValueError('Invalid OHLCV')
            if not 0 < row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high'] or row['volume_base'] < 0: raise ValueError('Invalid OHLCV range')
        result[tf] = metrics(rows)
        result[tf]['close_time_utc'] = (stamp(rows[-1]['open_time_utc']) + dt.timedelta(seconds=seconds)).isoformat()
        if (stamp(btc['retrieved_at_utc']) - stamp(result[tf]['close_time_utc'])).total_seconds() > seconds: warnings.append('Hiányzó friss lezárt gyertya: ' + tf)
    changes = compare(latest, history, 24)
    if changes is None: warnings.append('Még nincs összehasonlítható 24 órás dominanciaelőzmény; változás és trend nem állapítható meg.')
    daily = btc['timeframes']['1D']
    provenance = folder / 'provenance.json'
    return {'generated_at_utc': now.isoformat(), 'report_date': now.astimezone(ZoneInfo('Europe/Budapest')).date().isoformat(), 'btc': {'exchange': btc['exchange'], 'retrieved_at_utc': btc['retrieved_at_utc'], 'age_minutes': age_btc, 'metrics': result, 'seven_day_low': min(r['low'] for r in daily[-7:]), 'seven_day_high': max(r['high'] for r in daily[-7:])}, 'dominance': latest, 'dominance_age_minutes': age_dom, 'history_count': len(history), 'change_24h': changes, 'warnings': warnings, 'provenance': json.loads(provenance.read_text(encoding='utf-8')) if provenance.exists() else {}}

def fmt(value, digits=2): return f'{value:,.{digits}f}'.replace(',', ' ')
def local(value): return stamp(value).astimezone(ZoneInfo('Europe/Budapest')).strftime('%Y.%m.%d. %H:%M:%S')

def report_sections(m):
    b, d = m['btc'], m['dominance']
    daily, four = b['metrics']['1D'], b['metrics']['4H']
    state = 'felett' if daily['close'] > daily['ema20'] else 'alatt'
    trend = 'emelkedő' if daily['close'] > daily['ema20'] > daily['ema50'] else ('csökkenő' if daily['close'] < daily['ema20'] < daily['ema50'] else 'vegyes')
    momentum = 'pozitív' if daily['macd_hist'] > 0 else 'negatív'
    sections = [
        ('Áttekintés', [f"A napi záróár {fmt(daily['close'])} USDT; az előző napi záráshoz képest {daily['change_pct']:+.2f}%. Ez lezárt gyertya, nem aktuális spot ár. A napi záróár az EMA20 {state} van; az ár/EMA20/EMA50 sorrend alapján a szerkezet {trend}. A napi MACD-hisztogram {momentum}; RSI(14): {fmt(daily['rsi14'])}.", f"A 4 órás utolsó záróár {fmt(four['close'])} USDT, RSI(14): {fmt(four['rsi14'])}. A két idősík más zárási időpontot jelent; az eltérés nem élő árváltozás."]),
        ('Figyelt szintek', [f"A hét lezárt napi gyertyájának sávja: {fmt(b['seven_day_low'])} - {fmt(b['seven_day_high'])} USDT. Napi EMA20: {fmt(daily['ema20'])}; EMA50: {fmt(daily['ema50'])}. A napi ATR(14): {fmt(daily['atr14'])} USDT ({fmt(daily['atr14']/daily['close']*100)}% a napi záróárhoz mérve).", 'A hét sávjának teteje fölötti lezárt 4H gyertya és a szint megtartása kitörési feltétel lehet. A sáv alja alatti zárás gyengülést jelezhet; a visszavétel érvénytelenítheti a letörést. A sávon belül nincs igazolt kitörés. Ezek feltételes technikai forgatókönyvek.']),
        ('Dominancia és piaci szélesség', [f"BTC-részesedés: {fmt(d['values']['BTC.D'])}%; ETH: {fmt(d['values']['ETH.D'])}%. A két stabilcoin együttes részesedése {fmt(d['values']['USDT.D']+d['values']['USDC.D'])}%. Ezek a jelenlegi CoinGecko-mintát írják le; önmagukban nem bizonyítanak tőkebeáramlást vagy altcoinrotációt.", 'A dominancia változása százalékpontban, a kapitalizáció változása százalékban szerepel. A 24 órás referencia legfeljebb 90 perccel térhet el a célidőtől; a tényleges időközt is feltüntetjük.' if m['change_24h'] else 'A gyűjtés indulása óta csak egy minta áll rendelkezésre, ezért nincs hiteles 24 órás változás, dominanciatrend vagy rotációs jelzés.' if m['history_count']==1 else 'Nincs megfelelő, körülbelül 24 órával korábbi minta; változást és rotációs jelzést nem számolunk.']),
        ('Módszertan és források', ['BTC: a tároló ellenőrzött BTC/USDT spot adatai, idősíkonként 200 lezárt gyertya. EMA: első záróárból indított simítás; az EMA200 a 200 mintás kezdőértékre érzékeny becslés. RSI és ATR: 14 periódusos Wilder-simítás. MACD: 12/26/9. A napi és heti gyertyahatárok UTC szerintiek.', 'CoinGecko /global: BTC.D, ETH.D, USDT.D, USDC.D százalékos részesedés; TOTAL USD-ben. TOTAL2 = TOTAL × (1 - BTC.D/100); TOTAL3 = TOTAL × (1 - (BTC.D + ETH.D)/100). A CoinGecko teljes lefedettségéből számolt pillanatképek, nem közvetlen TradingView CRYPTOCAP-gyertyák, és nem azonos indexek.', 'A források időpontja különböző. A jelentés nem közös időpontra szinkronizált kereskedési jelzés. Az óránkénti ütemezés késhet; hiányzó mintát nem interpolálunk. A teszt ellenőrzi az adatokat és a jelentéskészítést, jövőbeli hozamot nem tesztel.'])
    ]
    return sections

def make_pdf(m, output):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    fonts = [(Path('C:/Windows/Fonts/arial.ttf'),Path('C:/Windows/Fonts/arialbd.ttf')), (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))]
    normal, bold = next(pair for pair in fonts if all(p.exists() for p in pair))
    pdfmetrics.registerFont(TTFont('Report',str(normal))); pdfmetrics.registerFont(TTFont('ReportBold',str(bold)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitle',fontName='ReportBold',fontSize=23,leading=28,textColor=colors.HexColor('#123149'),spaceAfter=10))
    styles.add(ParagraphStyle(name='ReportHead',fontName='ReportBold',fontSize=12,leading=16,textColor=colors.HexColor('#137b80'),spaceBefore=12,spaceAfter=7))
    styles.add(ParagraphStyle(name='ReportBody',fontName='Report',fontSize=9.5,leading=13.5,spaceAfter=7))
    styles.add(ParagraphStyle(name='ReportSmall',fontName='Report',fontSize=8,leading=11,spaceAfter=5))
    story=[]
    def p(text,style='ReportBody'): story.append(Paragraph(escape(text),styles[style]))
    def table(rows,widths):
        cells=[[Paragraph(escape(str(cell)),styles['ReportSmall']) for cell in row] for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5f1f2')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#ccd9df')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t)
    sections=report_sections(m)
    p('SS CRYPTO | Napi jelentés','ReportTitle');p(m['report_date']+(' | TESZTFUTTATÁS' if m.get('test_report') else ''),'ReportHead')
    p('Készült: '+local(m['generated_at_utc'])+' (Europe/Budapest).','ReportSmall')
    for warning in m['warnings']:p('ADATÁLLAPOT: '+warning,'ReportSmall')
    p(sections[0][0],'ReportHead')
    for text in sections[0][1]:p(text)
    table([['Lezárt gyertyák','4H','1D','1W']]+[[label]+[fmt(m['btc']['metrics'][tf][key]) for tf in TF] for label,key in [('Záróár (USDT)','close'),('Változás az előző záróhoz (%)','change_pct'),('EMA20','ema20'),('EMA50','ema50'),('EMA200 (becslés)','ema200'),('RSI(14)','rsi14'),('MACD-hisztogram','macd_hist'),('ATR(14), USDT','atr14')]],[185,110,110,110])
    p('BTC-forrás: '+m['btc']['exchange']+' | Adatfelvétel: '+local(m['btc']['retrieved_at_utc'])+' Budapest.','ReportSmall')
    for tf in TF:p(tf+' utolsó gyertya zárási ideje: '+local(m['btc']['metrics'][tf]['close_time_utc'])+' Budapest.','ReportSmall')
    story.append(PageBreak());p('Dominancia és összpiac','ReportTitle')
    p('CoinGecko forrásidő: '+local(m['dominance']['source_updated_at'])+' | Gyűjtés: '+local(m['dominance']['observed_at'])+' Budapest.','ReportSmall')
    rows=[['Mutató','Érték','24 órás változás']]
    for key in KEYS:
        value=fmt(m['dominance']['values'][key])+(' %' if key.endswith('.D') else ' USD')
        change='Nincs referencia' if not m['change_24h'] else f"{m['change_24h']['changes'][key]:+.3f}"+(' százalékpont' if key.endswith('.D') else ' %')
        rows.append([key,value,change])
    table(rows,[90,255,170])
    if m['change_24h']: p('Referencia: '+local(m['change_24h']['baseline_at'])+f" Budapest; tényleges időköz: {m['change_24h']['interval_hours']:.2f} óra.",'ReportSmall')
    for text in sections[2][1]:p(text)
    p(sections[1][0],'ReportHead')
    for text in sections[1][1]:p(text)
    story.append(PageBreak());p('Adatminőség és ellenőrzés','ReportTitle')
    table([['Ellenőrzés','Eredmény'],['BTC-adatok', '3 idősík; mindegyiken legalább 200 lezárt, folytonos OHLCV-gyertya.'],['Dominancia','7 pozitív, véges érték; TOTAL2/TOTAL3 képletek egyeznek.'],['Előzmény',f"{m['history_count']} minta; a legutóbbi megegyezik a latest fájllal."],['Frissesség',f"BTC: {m['btc']['age_minutes']:.0f} perc; dominancia: {m['dominance_age_minutes']:.0f} perc a készítéskor."],['24 órás összehasonlítás','Elérhető' if m['change_24h'] else 'Még nem elérhető; nincs kitalált változás.']],[150,365])
    p(sections[3][0],'ReportHead')
    for text in sections[3][1]:p(text)
    ref=m['provenance'].get('commit','main')
    for label,name in [('BTC-adatok','ss_crypto_btc_ohlcv.json'),('Dominancia','ss_crypto_dominance_latest.json'),('Havi előzmény','data/dominance/'+m['dominance']['source_updated_at'][:7]+'.json')]:
        url=BASE+ref+'/'+name
        story.append(Paragraph(f'<link href="{url}" color="#137b80">{label}: GitHub, rögzített forrás</link>',styles['ReportSmall']))
    url='https://docs.coingecko.com/demo/reference/crypto-global'
    story.append(Paragraph(f'<link href="{url}" color="#137b80">CoinGecko /global dokumentáció</link>',styles['ReportSmall']))
    if m['provenance'].get('commit'):p('Forrás-commit: '+ref,'ReportSmall')
    p('Tájékoztató technikai elemzés; nem személyre szabott befektetési tanács.','ReportSmall')
    def footer(canvas,doc):
        canvas.setFont('Report',8);canvas.setFillColor(colors.HexColor('#607889'));canvas.drawString(40,24,'SS CRYPTO | '+m['report_date']+' | Napi jelentés'+(' teszt' if m.get('test_report') else ''));canvas.drawRightString(555,24,str(doc.page))
    SimpleDocTemplate(str(output),pagesize=(595.28,841.89),leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=42,title='SS CRYPTO napi jelentés - '+m['report_date'],author='SS CRYPTO').build(story,onFirstPage=footer,onLaterPages=footer)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-dir',type=Path,default=Path('.'));parser.add_argument('--output-dir',type=Path,default=Path('reports'));parser.add_argument('--fetch',action='store_true');parser.add_argument('--pdf',action='store_true');parser.add_argument('--test-report',action='store_true');args=parser.parse_args()
    if args.fetch:fetch_inputs(args.input_dir)
    model=build_model(args.input_dir);model['test_report']=args.test_report;args.output_dir.mkdir(parents=True,exist_ok=True)
    stem='SS_CRYPTO_napi_jelentes_'+model['report_date']+('_teszt' if args.test_report else '')
    (args.output_dir/(stem+'.json')).write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
    parts=['# SS CRYPTO napi jelentés | '+model['report_date'],('TESZTFUTTATÁS. ' if args.test_report else '')+'Készült: '+local(model['generated_at_utc'])+' Budapest.']
    parts+=['Adatállapot: '+w for w in model['warnings']]
    for title,texts in report_sections(model):parts+=['## '+title,*texts]
    table_lines=['| Mutató | Érték | 24h változás |','|---|---:|---:|']
    for key in KEYS:
        change='Nincs referencia' if model['change_24h'] is None else fmt(model['change_24h']['changes'][key])+(' százalékpont' if key.endswith('.D') else ' %')
        table_lines.append('| '+key+' | '+fmt(model['dominance']['values'][key])+(' %' if key.endswith('.D') else ' USD')+' | '+change+' |')
    parts.append('\n'.join(table_lines))
    parts+=['BTC adatfelvétel: '+local(model['btc']['retrieved_at_utc']), 'Dominancia forrásidő: '+local(model['dominance']['source_updated_at']), 'Forrás-commit: '+model['provenance'].get('commit','helyi másolat'), '[CoinGecko módszertan](https://docs.coingecko.com/demo/reference/crypto-global)', '[Tároló](https://github.com/RudolfHss/ss-crypto)']
    (args.output_dir/(stem+'.md')).write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    if args.pdf:make_pdf(model,args.output_dir/(stem+'.pdf'))
    print(json.dumps({'date':model['report_date'],'warnings':model['warnings'],'history_count':model['history_count'],'output':str(args.output_dir)},ensure_ascii=False))

if __name__=='__main__':main()
