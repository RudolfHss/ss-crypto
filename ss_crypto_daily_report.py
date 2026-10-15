"""Audited SS CRYPTO report. One document model renders JSON, Markdown and PDF."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from ss_crypto_analysis import UTC, PERIODS, QUALITY, timestamp, age_status, finite, analyse_btc

KEYS=['BTC.D','ETH.D','USDT.D','USDC.D','TOTAL','TOTAL2','TOTAL3']
UNIVERSE=['ethereum','solana','binancecoin','ripple','dogecoin','cardano','chainlink','avalanche-2','polkadot','uniswap','litecoin','near']
UNIVERSE_VERSION='fixed-v1-2026-10-15'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def unavailable(reason):return {'status':'nem értékelhető','reasons':[reason]}

def validate_sample(sample):
    if sample.get('schema_version')!=1 or sample.get('source')!='CoinGecko /global':raise ValueError('Invalid dominance schema/source')
    source=timestamp(sample['source_updated_at']);observed=timestamp(sample['observed_at'])
    if source>observed+dt.timedelta(minutes=5):raise ValueError('Dominance source timestamp exceeds observation')
    v=sample['values']
    if set(v)!=set(KEYS) or any(not finite(v[k]) or v[k]<=0 for k in KEYS):raise ValueError('Missing/invalid dominance value')
    if any(v[k]>=100 for k in KEYS[:4]) or sum(v[k] for k in KEYS[:4])>100:raise ValueError('Invalid dominance percentages')
    for key,want in [('TOTAL2',v['TOTAL']*(1-v['BTC.D']/100)),('TOTAL3',v['TOTAL']*(1-(v['BTC.D']+v['ETH.D'])/100))]:
        if not math.isclose(v[key],want,rel_tol=1e-9):raise ValueError('Inconsistent '+key)

def compare(latest,history,hours=24):
    end=timestamp(latest['source_updated_at']);target=end-dt.timedelta(hours=hours)
    candidates=[r for r in history if timestamp(r['source_updated_at'])<end and abs((timestamp(r['source_updated_at'])-target).total_seconds())<=5400]
    if not candidates:return None
    before=min(candidates,key=lambda r:abs((timestamp(r['source_updated_at'])-target).total_seconds()))
    return {'baseline_at':before['source_updated_at'],'interval_hours':(end-timestamp(before['source_updated_at'])).total_seconds()/3600,'changes':{k:latest['values'][k]-before['values'][k] if k.endswith('.D') else (latest['values'][k]/before['values'][k]-1)*100 for k in KEYS}}

def analyse_dominance(folder,now):
    latest=read(folder/'ss_crypto_dominance_latest.json');validate_sample(latest)
    status,age=age_status(timestamp(latest['source_updated_at']),now,7200)
    observation_status,observation_age=age_status(timestamp(latest['observed_at']),now,7200)
    history=[];seen={}
    for path in sorted((folder/'data/dominance').glob('*.json')):
        rows=read(path)
        if not isinstance(rows,list):raise ValueError('Invalid dominance history')
        for row in rows:
            validate_sample(row)
            key=row['source_updated_at']
            if key in seen and seen[key]!=row:raise ValueError('Conflicting duplicate dominance sample')
            seen[key]=row
    for row in seen.values():
        if timestamp(row['source_updated_at'])<=now and timestamp(row['observed_at'])<=now:history.append(row)
    if not any(r==latest for r in history):raise ValueError('Latest not present in point-in-time dominance history')
    status=max([status,observation_status],key=QUALITY.get)
    return {'status':status,'reasons':[] if status=='friss' else ['Elavult dominanciaforrás vagy lekérés.'],'sample':latest,'source_age_seconds':age,'observation_age_seconds':observation_age,'history_count':len(history),'change_24h':compare(latest,history)}

def analyse_context(folder,now):
    sample=read(folder/'ss_crypto_context.json')
    if sample.get('schema_version')!=1 or sample.get('source')!='CoinGecko /coins/markets' or sample.get('universe_version')!=UNIVERSE_VERSION or sample.get('universe')!=UNIVERSE:raise ValueError('Invalid context schema/universe')
    observation_status,_=age_status(timestamp(sample['observed_at']),now,7200)
    parts={}
    for key in ['stablecoin_caps','eth_btc','breadth']:
        try:
            c=sample['components'][key]
            if c.get('status')!='available':raise ValueError(c.get('reason','Missing component'))
            source_times=[]
            if key=='stablecoin_caps':
                for symbol in ['USDT','USDC']:
                    value=c['values'][symbol]
                    if not finite(value['usd']) or value['usd']<=0:raise ValueError('Invalid absolute stablecoin cap')
                    source_times.append(timestamp(value['source_updated_at']))
            elif key=='eth_btc':
                if not finite(c['ratio']) or c['ratio']<=0 or not finite(c['relative_change_24h_pct']):raise ValueError('Invalid ETH/BTC cross-rate')
                source_times.append(timestamp(c['source_updated_at']))
            else:
                obs=c['observations']
                if len(obs)!=len(UNIVERSE) or sorted(r['id'] for r in obs)!=sorted(UNIVERSE):raise ValueError('Incomplete fixed universe')
                if any(not finite(r['return_24h_pct']) for r in obs):raise ValueError('Invalid breadth return')
                count=sum(r['return_24h_pct']>0 for r in obs)
                if c['denominator']!=12 or c['coverage']!=12 or c['advancing']!=count or not math.isclose(c['positive_pct'],count/12*100):raise ValueError('Inconsistent participation calculation')
                source_times.extend(timestamp(r['source_updated_at']) for r in obs)
                if (max(source_times)-min(source_times)).total_seconds()>600:raise ValueError('Unsynchronised breadth rows')
            statuses=[age_status(t,now,7200)[0] for t in source_times]+[observation_status]
            status=max(statuses,key=QUALITY.get)
            parts[key]={'status':status,'data':c,'reasons':[] if status=='friss' else ['A kiegészítő forrás nem friss.']}
        except (ValueError,KeyError,TypeError) as error:parts[key]={'status':'korlátozott','data':None,'reasons':[str(error)]}
    return {'status':max([p['status'] for p in parts.values()],key=QUALITY.get),'observed_at':sample['observed_at'],'universe_version':UNIVERSE_VERSION,'components':parts,'reasons':[]}

def build_model(folder,now=None,previous=None,test_report=False):
    folder=Path(folder);now=now or dt.datetime.now(UTC)
    try:btc=analyse_btc(read(folder/'ss_crypto_btc_ohlcv.json'),now)
    except (ValueError,KeyError,TypeError,OSError) as error:btc=unavailable(str(error))
    try:dominance=analyse_dominance(folder,now)
    except (ValueError,KeyError,TypeError,OSError) as error:dominance=unavailable(str(error))
    try:context=analyse_context(folder,now)
    except (ValueError,KeyError,TypeError,OSError) as error:context={'status':'korlátozott','reasons':[str(error)],'components':{}}
    state=max([btc['status'],dominance['status'],context['status']],key=QUALITY.get)
    reasons=[]
    for name,component in [('BTC',btc),('Dominancia',dominance),('Kiegészítő környezet',context)]:
        reasons.extend(name+': '+r for r in component.get('reasons',[]))
        for tf,item in component.get('timeframes',{}).items():reasons.extend(tf+': '+r for r in item.get('reasons',[]))
        for name2,item in component.get('components',{}).items():reasons.extend(name2+': '+r for r in item.get('reasons',[]))
    if dominance.get('sample') and dominance.get('change_24h') is None:reasons.append('Nincs összehasonlítható 24 órás dominanciaminta; dominanciatrendet nem állítunk.')
    prior=None
    if previous:
        try:
            candidate=read(previous) if isinstance(previous,(str,Path)) else previous
            if candidate.get('schema_version')==2 and timestamp(candidate['generated_at_utc'])<now:prior=candidate
            else:reasons.append('A korábbi jelentés nem összehasonlítható vagy későbbi időpontú.')
        except (ValueError,KeyError,TypeError,OSError):reasons.append('A korábbi jelentés nem olvasható; változás nincs kiszámítva.')
    changes={'available':False,'reason':'Nincs korábbi, összehasonlítható jelentés.','level_changes':None}
    switched=bool(read(folder/'ss_crypto_btc_ohlcv.json').get('source_changed')) if btc.get('exchange') else False
    if prior and btc.get('levels') and prior.get('btc',{}).get('levels'):
        switched=switched or prior['btc'].get('exchange')!=btc.get('exchange')
        if not switched:
            changes={'available':True,'baseline_at':prior['generated_at_utc'],'level_changes':{k:v-prior['btc']['levels'][k] for k,v in btc['levels'].items()},'reason':'Azonos tőzsde, az előző jelentéshez mért USDT-szintváltozás. Volumeneket nem vonunk össze.'}
        else:changes['reason']='Forrásváltás: a korábbi tőzsde árszintje és volumene nem közvetlenül összehasonlítható.'
    if switched:reasons.append('Forrásváltás történt; korábbi tőzsdei volumenhez nincs összehasonlítás.')
    allowed=state=='friss'
    scenarios=[]
    if btc.get('scenario_range'):
        r=btc['scenario_range'];lo,hi=r['lower'],r['upper'];a,b=r['last_two_closes']
        rvol=btc['timeframes']['4H']['indicators']['rvol20']
        for name,condition,invalid,met in [
            ('Emelkedő',f'Két egymást követő lezárt 4H zárás {fmt(hi)} USDT felett és a második gyertyán RVOL20 legalább 1,20.',f'Következő lezárt 4H zárás {fmt(hi)} USDT alatt.',a>hi and b>hi and rvol is not None and rvol>=1.2),
            ('Eső',f'Két egymást követő lezárt 4H zárás {fmt(lo)} USDT alatt és a második gyertyán RVOL20 legalább 1,20.',f'Következő lezárt 4H zárás {fmt(lo)} USDT felett.',a<lo and b<lo and rvol is not None and rvol>=1.2),
            ('Oldalazó',f'Az utolsó két lezárt 4H zárás a {fmt(lo)} - {fmt(hi)} USDT sávban és RVOL20 1,20 alatt.',f'Lezárt 4H zárás a sávon kívül; az irány megerősítése külön szükséges.',lo<=a<=hi and lo<=b<=hi and rvol is not None and rvol<1.2)]:
            scenarios.append({'name':name,'confirmation':condition,'invalidation':invalid,'condition_observed':bool(met) if allowed else None,'evaluation':'lezárt gyertyás feltétel teljesül' if allowed and met else 'feltétel nem teljesül' if allowed else 'adatkapu miatt nem aktiválható; történeti szintek','trade_signal':False})
    else:scenarios=[{'name':'Nem értékelhető','confirmation':'Érvényes, friss 4H adatsor szükséges.','invalidation':'Hiányos, hibás vagy elavult adatsor.','condition_observed':None,'evaluation':'nincs értékelhető forgatókönyv','trade_signal':False}]
    provenance={}
    try:provenance=read(folder/'provenance.json')
    except (OSError,ValueError):pass
    failures=provenance.get('collection_failures',[])
    if failures:
        state=max([state,'korlátozott'],key=QUALITY.get)
        allowed=False
        reasons.extend('A mostani gyűjtés sikertelen: '+name+'; az esetleg megmaradt adat történeti.' for name in failures)
        for s in scenarios:
            s['condition_observed']=None;s['evaluation']='adatkapu miatt nem aktiválható; történeti szintek'
    model={'schema_version':2,'generated_at_utc':now.isoformat(),'report_date':now.astimezone(ZoneInfo('Europe/Budapest')).date().isoformat(),'test_report':test_report,'data_status':state,'historical_summary_only':not allowed,'current_analysis_allowed':allowed,'new_trade_signal':False,'reasons':reasons,'btc':btc,'dominance':dominance,'context':context,'source_changed':switched,'previous_report_comparison':changes,'scenarios':scenarios,'provenance':provenance}
    model['document']=document(model)
    model['content_sha256']=hashlib.sha256(json.dumps(model['document'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return model

def fmt(value,digits=2):return 'nem elérhető' if value is None else f'{value:,.{digits}f}'.replace(',',' ')
def local(value):return timestamp(value).astimezone(ZoneInfo('Europe/Budapest')).strftime('%Y.%m.%d. %H:%M:%S')

def document(m):
    blocks=[]
    def head(s):blocks.append({'type':'heading','text':s})
    def p(s,keep=False):blocks.append({'type':'paragraph','text':s,'keep_with_next':keep})
    def table(rows,widths=None):blocks.append({'type':'table','rows':rows,'widths':widths})
    head('1. Adatállapot')
    p('Állapot: '+m['data_status'].upper()+'. '+('Történeti összefoglaló; aktuális piaci ajánlás és új trade jelzés nem keletkezik.' if m['historical_summary_only'] else 'Friss, lezárt gyertyás napi értékelés; ez nem élő scalp/daytrade szolgáltatás.'))
    p('Készült: '+local(m['generated_at_utc'])+' (Europe/Budapest).'+(' TESZTFUTTATÁS.' if m['test_report'] else ''))
    table([['Adatmodul','Állapot'],['BTC/USDT',m['btc']['status']],['CoinGecko dominancia',m['dominance']['status']],['Kiegészítő BTC/alt környezet',m['context']['status']]],[300,215])
    for reason in m['reasons']:p(reason)
    b=m['btc'];frames=b.get('timeframes',{})
    if b.get('retrieved_at_utc'):p('BTC-lekérés: '+local(b['retrieved_at_utc'])+' Budapest; tőzsde: '+b['exchange']+'.')
    for tf in ['1W','1D','4H']:
        item=frames.get(tf,{})
        p(tf+': utolsó lezárt gyertya '+(local(item['last_close_utc']) if item.get('last_close_utc') else 'nem értékelhető')+'; elvárt zárás '+(local(item['expected_close_utc']) if item.get('expected_close_utc') else 'nem értékelhető')+' Budapest. Állapot: '+item.get('status','nem értékelhető')+'.')
    head('2. Heti háttér, napos trend, 4H megerősítés')
    for tf,label in [('1W','Heti háttér'),('1D','Napos trend'),('4H','4H megerősítés')]:
        item=frames.get(tf,{});v=item.get('indicators')
        if not v:p(label+': az adatsor nem értékelhető.');continue
        p(f"{label}: csúcs-mélypont szerkezet {v['structure']['state']}; külön EMA-sorrend: {v['ema_order']}. Utolsó záróár {fmt(v['close'])} USDT; előző gyertyához képest {v['change_pct']:+.2f}%. RSI14 {fmt(v['rsi14'])}, MACD-hisztogram {fmt(v['macd_hist'])}; RVOL20 {fmt(v['rvol20'])}.")
        if v['ema200'] is None:p(f"{tf} EMA200 nem közölt: {item['count']} gyertya áll rendelkezésre a kért 1000-es bemelegítés helyett. Nem használjuk trendbizonyítékként.")
    valid=[tf for tf in ['1W','1D','4H'] if frames.get(tf,{}).get('indicators')]
    if valid:
        table([['Mutató']+valid]+[[label]+[fmt(frames[tf]['indicators'][key]) for tf in valid] for label,key in [('Záróár (USDT)','close'),('EMA20','ema20'),('EMA50','ema50'),('EMA200 (1000+ minta)','ema200'),('RSI14','rsi14'),('MACD-hisztogram','macd_hist'),('ATR14 (USDT)','atr14'),('RVOL20','rvol20')]])
        states=[frames[tf]['indicators']['structure']['state'] for tf in valid]
        p('Idősíkok viszonya: '+('a megerősített szerkezet besorolása egyezik.' if len(set(states))==1 else 'eltérő vagy vegyes szerkezet; nincs egységes trendmegerősítés.'))
        for tf in valid:
            s=frames[tf]['indicators']['structure']
            for kind,label in [('highs','csúcs'),('lows','mélypont')]:
                if s[kind]:p(tf+' utolsó megerősített '+label+': '+fmt(s[kind][-1]['price'])+' USDT; csak '+local(s[kind][-1]['confirmed_at'])+' Budapest után volt ismert.')
    head('3. Kulcsszintek és változás az előző jelentéshez')
    changes=m['previous_report_comparison'];p(changes['reason'])
    if changes.get('baseline_at'):p('Referenciajelentés: '+local(changes['baseline_at'])+' Budapest.')
    labels={'seven_day_low':'7 lezárt napi gyertya minimuma','seven_day_high':'7 lezárt napi gyertya maximuma','ema20':'Napi EMA20','ema50':'Napi EMA50'}
    rows=[['Szint','USDT','Változás (USDT)']]
    for key,value in b.get('levels',{}).items():rows.append([labels[key],fmt(value),fmt(changes['level_changes'][key]) if changes.get('available') else 'nem összehasonlítható'])
    if len(rows)>1:table(rows,[250,125,140])
    head('4. BTC- és altcoin-környezet')
    d=m['dominance']
    if d.get('sample'):
        sample=d['sample'];p('CoinGecko forrásidő: '+local(sample['source_updated_at'])+'; lekérés: '+local(sample['observed_at'])+' Budapest. A hét mutató részben algebrailag összefügg, nem hét független jel.')
        rows=[['Mutató','Érték','Kb. 24h változás']]
        for key in KEYS:
            unit=' %' if key.endswith('.D') else ' USD'
            delta='nincs referencia' if d['change_24h'] is None else fmt(d['change_24h']['changes'][key],3)+(' százalékpont' if key.endswith('.D') else ' %')
            rows.append([key,fmt(sample['values'][key])+unit,delta])
        table(rows,[75,240,200])
        if d.get('change_24h'):p('24h referencia: '+local(d['change_24h']['baseline_at'])+' Budapest; tényleges időköz '+fmt(d['change_24h']['interval_hours'])+' óra.')
    else:p('A dominanciaadat nem értékelhető; nem közlünk helyettesítő számokat.')
    components=m['context'].get('components',{})
    for key,title in [('eth_btc','ETH/BTC relatív erő'),('stablecoin_caps','Stabilcoinok abszolút kapitalizációja'),('breadth','Rögzített altcoin-univerzum részvétele')]:
        c=components.get(key,{});v=c.get('data')
        if not v or c.get('status')!='friss':p(title+': hiányzó vagy nem friss adat; aktuális következtetés nem készül.');continue
        if key=='eth_btc':p(title+': '+fmt(v['ratio'],6)+' BTC/ETH; gördülő 24h relatív változás '+fmt(v['relative_change_24h_pct'],3)+'%. USD-jegyzésekből származtatott keresztárfolyam, nem tőzsdei ETH/BTC-gyertya.')
        elif key=='stablecoin_caps':
            for symbol,item in v['values'].items():p(symbol+': '+fmt(item['usd'])+' USD; forrásidő '+local(item['source_updated_at'])+' Budapest. A kapitalizáció önmagában nem bizonyít tőkeáramlást.')
        else:p(title+f": {v['advancing']}/{v['denominator']} pozitív gördülő 24h USD-hozam, {fmt(v['positive_pct'])}%; teljes lefedettség {v['coverage']}/12. Univerzum: "+', '.join(UNIVERSE)+'. A sorozat 2026.10.15-től épül; nincs visszamenőleg kitalált univerzum.')
    head('5. Feltételes forgatókönyvek')
    p('Nincs vételi/eladási megbízás vagy új trade jelzés. Az adatkapu '+('enged lezárt gyertyás feltételértékelést.' if m['current_analysis_allowed'] else 'tiltja az aktuális aktiválást; a következő szintek történeti megfigyelési keretek.'))
    for s in m['scenarios']:
        p(s['name']+' - '+s['evaluation']+'.',True)
        p('Megerősítés: '+s['confirmation'],True);p('Érvénytelenítés: '+s['invalidation'])
    head('6. Módszertan, korlátok és elérhetőség')
    for text in [
        'UTC gyertyahatárok: nap 00:00, hét hétfő 00:00. Az elvárt utolsó zárást az értékelés ideje előtt 5 perccel számoljuk, hogy legyen szolgáltatói lezárási türelem. Napi/heti zárást nem várunk a periódus befejezése előtt.',
        'BTC-lekérés: 90 percig friss, 90 perc és 24 óra között korlátozott, 24 óra felett nem értékelhető. CoinGecko forrás és lekérés: 120 percig friss; 24 óráig korlátozott; utána nem értékelhető. Hibás/hiányos alapadat nem értékelhető, hiányzó kiegészítő modul korlátozott. 5 percnél távolabbi jövőbeli időbélyeg hibás.',
        'Szerkezet: szigorú két bal/két jobb gyertyás csúcsok és mélypontok. A pivot csak a két jobb gyertya zárása után ismert. Az utolsó két megerősített csúcs és mélypont együttes HH/HL vagy LH/LL viszonya ad besorolást. Az EMA-sorrend külön trendleíró, nem piaci szerkezet.',
        'EMA: első rendelkezésre álló záróárral inicializálva; EMA200 csak legalább 1000 lezárt gyertyából. Az induló érték súlya ekkor legfeljebb (199/201)^999, körülbelül 0,0046%. Rövidebb heti tőzsdei történetnél EMA200 nincs közölve. RSI14 és ATR14 Wilder-simítás, MACD 12/26/9. Az összefüggő indikátorokat nem pontozzuk független bizonyítékként.',
        'RVOL20: az utolsó gyertya BTC-alapvolumene osztva a megelőző húsz lezárt gyertya átlagával, azonos tőzsdén és idősíkon. Megerősítési küszöb 1,20; ez szabály, nem bizonyított hozamelőny. Forrásváltáskor tőzsdék volumene nem keverhető.',
        'CoinGecko TOTAL2 = TOTAL × (1 - BTC.D/100); TOTAL3 = TOTAL × (1 - (BTC.D + ETH.D)/100). Ezek CoinGecko-pillanatképek, nem TradingView CRYPTOCAP-gyertyák vagy azonos indexek. A dominancia önmagában nem tőkeáramlás. Részvétel: a rögzített 12 érme pozitív gördülő 24h USD-hozamának egyenlő darabszámú aránya, nem TOTAL3 és nem teljes altcoinpiaci lefedettség.',
        'A 07:30 Europe/Budapest reggeli időpont következetes napi értékelési idő, nem konkrét tőzsdenyitásra optimalizált. GitHub Actions késhet. A 4H/1D/1W spotadat nem élő scalp/daytrade/perpetual adatfolyam. Ilyen szolgáltatás nincs bekapcsolva.',
        'Források: Coinbase Exchange /products/BTC-USDT/candles; OKX /api/v5/market/history-candles UTC barokkal; Bybit /v5/market/kline spot; CoinGecko /api/v3/global és /api/v3/coins/markets. A tényleges tőzsde és az adatok időpontja fent szerepel.',
        'Tájékoztató technikai értékelés; nem személyre szabott befektetési tanács.'
    ]:p(text)
    if m['provenance']:p('Adateredet: '+json.dumps(m['provenance'],ensure_ascii=False,sort_keys=True))
    return blocks

def make_pdf(model,path):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,KeepTogether,Spacer
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from xml.sax.saxutils import escape
    pairs=[('C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/arialbd.ttf'),('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
    normal,bold=next(pair for pair in pairs if all(Path(f).exists() for f in pair))
    pdfmetrics.registerFont(TTFont('Report',normal));pdfmetrics.registerFont(TTFont('ReportBold',bold))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RTitle',fontName='ReportBold',fontSize=22,leading=27,textColor=colors.HexColor('#123149'),spaceAfter=11))
    styles.add(ParagraphStyle(name='RHead',fontName='ReportBold',fontSize=12,leading=16,textColor=colors.HexColor('#14777d'),spaceBefore=12,spaceAfter=7,keepWithNext=True))
    styles.add(ParagraphStyle(name='RBody',fontName='Report',fontSize=9,leading=13,spaceAfter=7,splitLongWords=True))
    styles.add(ParagraphStyle(name='RKeep',parent=styles['RBody'],keepWithNext=True))
    styles.add(ParagraphStyle(name='RCell',fontName='Report',fontSize=8,leading=11,spaceAfter=0))
    story=[Paragraph('SS CRYPTO | Napi jelentés',styles['RTitle']),Paragraph(model['report_date']+(' | AUDIT TESZT' if model['test_report'] else ''),styles['RHead'])]
    for block in model['document']:
        if block['type']=='heading':story.append(Paragraph(escape(block['text']),styles['RHead']))
        elif block['type']=='paragraph':story.append(Paragraph(escape(block['text']),styles['RKeep'] if block.get('keep_with_next') else styles['RBody']))
        else:
            rows=[[Paragraph(escape(str(c)),styles['RCell']) for c in row] for row in block['rows']]
            widths=block.get('widths') or [515/len(rows[0])]*len(rows[0])
            t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6f1f2')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#cedde2')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story+=[t,Spacer(1,6)]
    story.append(Paragraph('Tartalomazonosító: '+model['content_sha256'],styles['RCell']))
    def footer(canvas,doc):
        canvas.setFont('Report',8);canvas.setFillColor(colors.HexColor('#5b7485'));canvas.drawString(40,24,'SS CRYPTO | '+model['report_date']+' | '+model['data_status']);canvas.drawRightString(555,24,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=(595.28,841.89),leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=42,title='SS CRYPTO napi jelentés '+model['report_date'],author='SS CRYPTO').build(story,onFirstPage=footer,onLaterPages=footer)

def export(model,folder,pdf=True):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    name='SS_CRYPTO_napi_jelentes_'+model['report_date']+('_audit_teszt' if model['test_report'] else '')
    parts=['# SS CRYPTO napi jelentés | '+model['report_date']]
    for block in model['document']:
        if block['type']=='heading':parts.append('## '+block['text'])
        elif block['type']=='paragraph':parts.append(block['text'])
        else:
            rows=block['rows'];parts.append('\n'.join(['| '+' | '.join(str(c).replace('|','/') for c in rows[0])+' |','|'+'---|'*len(rows[0])]+['| '+' | '.join(str(c).replace('|','/') for c in row)+' |' for row in rows[1:]]))
    parts.append('Tartalomazonosító: '+model['content_sha256'])
    (folder/(name+'.json')).write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/(name+'.md')).write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    if pdf:make_pdf(model,folder/(name+'.pdf'))
    return folder/(name+'.json')

def verify_outputs(model_path):
    from pypdf import PdfReader
    path=Path(model_path);m=read(path)
    if hashlib.sha256(json.dumps(m['document'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=m['content_sha256']:raise AssertionError('JSON document hash differs')
    md=path.with_suffix('.md').read_text(encoding='utf-8')
    pdf=PdfReader(path.with_suffix('.pdf'));text=' '.join('\n'.join(p.extract_text() for p in pdf.pages).split())
    for block in m['document']:
        values=[str(c) for row in block['rows'] for c in row] if block['type']=='table' else [block['text']]
        for value in values:
            if ' '.join(value.split()) not in text:raise AssertionError('PDF missing content: '+value[:80])
            if value.replace('|','/') not in md and value not in md:raise AssertionError('Markdown missing content: '+value[:80])
    if m['data_status']!='friss':
        assert not m['current_analysis_allowed'] and m['historical_summary_only']
        assert all(s['condition_observed'] is None for s in m['scenarios'])
    assert m['new_trade_signal'] is False
    print(json.dumps({'verified':True,'pages':len(pdf.pages),'status':m['data_status'],'content_sha256':m['content_sha256']},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser();p.add_argument('--input-dir',type=Path,default=Path('.'));p.add_argument('--output-dir',type=Path,default=Path('reports'));p.add_argument('--previous',type=Path);p.add_argument('--test-report',action='store_true');p.add_argument('--pdf',action='store_true');p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:verify_outputs(a.verify);return
    model=build_model(a.input_dir,previous=a.previous,test_report=a.test_report)
    path=export(model,a.output_dir,a.pdf);print(json.dumps({'model':str(path),'status':model['data_status'],'current_analysis_allowed':model['current_analysis_allowed']},ensure_ascii=False))

if __name__=='__main__':main()
