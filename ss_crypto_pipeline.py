"""Daily data collection -> quality model -> consistent report -> verification."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo
from ss_crypto_analysis import UTC
from ss_crypto_daily_report import build_model, export, verify_outputs

ROOT=Path(__file__).resolve().parent

def schedule_decision(now,cron,already_exists=False):
    local=now.astimezone(ZoneInfo('Europe/Budapest'))
    due=local.replace(hour=7,minute=30,second=0,microsecond=0).astimezone(UTC)
    wanted=f'30 {due.hour} * * *'
    if cron!=wanted:return False,'A másik UTC-időpont tartozik a mai magyar időszámításhoz.'
    if now<due:return False,'A mai 07:30 magyar idő még nem érkezett el.'
    if already_exists:return False,'A mai rendes jelentés már megvan; nincs duplikálás.'
    return True,'07:30 Europe/Budapest napi futás; késleltetett indulás megengedett.'

def collect(work,existing=False):
    work.mkdir(parents=True,exist_ok=True)
    if not existing:
        for name in ['ss_crypto_btc_ohlcv.json','ss_crypto_dominance_latest.json','ss_crypto_context.json']:
            if (ROOT/name).exists():shutil.copy2(ROOT/name,work/name)
        if (ROOT/'data').exists():shutil.copytree(ROOT/'data',work/'data',dirs_exist_ok=True)
    results={}
    if not existing:
        for key,command,timeout in [('btc',[sys.executable,str(ROOT/'ss_crypto_market_data.py')],660),('dominance_context',['node',str(ROOT/'ss_crypto_dominance.mjs')],300)]:
            try:
                result=subprocess.run(command,cwd=work,text=True,capture_output=True,timeout=timeout,encoding='utf-8',errors='replace')
                results[key]={'returncode':result.returncode,'log':(result.stdout+'\n'+result.stderr)[-4000:]}
            except (subprocess.SubprocessError,OSError) as error:results[key]={'returncode':1,'log':str(error)}
    failures=[k for k,v in results.items() if v['returncode']!=0]
    evidence={'code_commit':os.environ.get('GITHUB_SHA','local-audit-build'),'run_url':('https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else 'local-verified-run','data_mode':'live provider snapshots' if not existing else 'recorded real provider snapshots','collection_failures':failures}
    (work/'provenance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    (work/'collection_health.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return evidence

def run(work,output,test_report=True,existing=False,previous=None):
    collect(work,existing)
    model=build_model(work,previous=previous,test_report=test_report)
    path=export(model,output,pdf=True);verify_outputs(path)
    if not test_report:
        latest=ROOT/'reports/latest.json';latest.parent.mkdir(parents=True,exist_ok=True)
        latest.write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
        rel=path.parent.relative_to(ROOT/'reports').as_posix()
        stem=path.stem
        (ROOT/'reports/README.md').write_text('# SS CRYPTO napi jelentés\n\nLegutóbbi értékelés: '+model['report_date']+' | Állapot: **'+model['data_status']+'**\n\n[PDF]('+rel+'/'+stem+'.pdf) · [Szöveg]('+rel+'/'+stem+'.md) · [Adatlap]('+rel+'/'+stem+'.json)\n\n07:30 Europe/Budapest; GitHub-késések lehetségesek. Ez lezárt gyertyás napi jelentés, nem élő kereskedési szolgáltatás.\n',encoding='utf-8')
    summary=f"SS CRYPTO: {model['data_status']}; historical_only={model['historical_summary_only']}; trade_signal=false"
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as handle:handle.write('## '+summary+'\n\nA PDF/Markdown/JSON és a felhasznált adatok a futás letölthető mentésében vannak.\n')
    print(summary);return path

def main():
    p=argparse.ArgumentParser();p.add_argument('--gate',action='store_true');p.add_argument('--cron',default='');p.add_argument('--work-dir',type=Path,default=ROOT/'run-data');p.add_argument('--output-dir',type=Path);p.add_argument('--use-existing',action='store_true');p.add_argument('--test-report',action='store_true');a=p.parse_args()
    now=dt.datetime.now(UTC);date=now.astimezone(ZoneInfo('Europe/Budapest')).date().isoformat()
    if a.gate:
        exists=any((ROOT/'reports'/date).glob('*.json'))
        decision,reason=schedule_decision(now,a.cron,exists)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as handle:handle.write('run='+str(decision).lower()+'\n')
        print(json.dumps({'run':decision,'reason':reason},ensure_ascii=False));return
    output=a.output_dir or ROOT/'reports'/('tests' if a.test_report else date)
    previous=ROOT/'reports/latest.json'
    run(a.work_dir.resolve(),output.resolve(),a.test_report,a.use_existing,previous if previous.exists() else None)

if __name__=='__main__':main()
