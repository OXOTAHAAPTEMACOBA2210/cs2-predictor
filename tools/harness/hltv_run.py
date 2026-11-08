# -*- coding: utf-8 -*-
"""Прогон HLTV-стенда в headless Chrome и печать отчёта #hp-report.

    python tools/harness/hltv_run.py [стенд.html ...]

Без аргументов — все собранноые стенды из tools/harness/hltv/.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
REPORT_RE = re.compile(r'<pre id="hp-report">(.*?)</pre>', re.S)


def run(path):
    url = 'file:///' + urllib.parse.quote(
        os.path.abspath(path).replace(os.sep, '/').lstrip('/'), safe='/:')
    cmd = [CHROME, '--headless=new', '--allow-file-access-from-files', '--disable-gpu',
           '--no-sandbox', '--virtual-time-budget=15000', '--timeout=40000', '--dump-dom', url]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding='utf-8', errors='replace').stdout
    m = REPORT_RE.search(out)
    if not m:
        return None, 'нет #hp-report (len=%d)' % len(out)
    raw = m.group(1)
    for pat, rep in (('&#39;', "'"), ('&quot;', '"'), ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>')):
        raw = raw.replace(pat, rep)
    try:
        return json.loads(raw.split('HP_STAND ', 1)[1]), None
    except ValueError as exc:
        return None, 'отчёт не парсится: %s' % exc


def main():
    args = sys.argv[1:]
    if not args:
        args = [os.path.join(HERE, 'hltv', f) for f in sorted(os.listdir(os.path.join(HERE, 'hltv')))
                if f.endswith('.html')]
    bad = 0
    for path in args:
        d, err = run(path)
        print('=' * 70)
        print(os.path.basename(path))
        if err:
            print('ОШИБКА:', err)
            bad += 1
            continue
        if d.get('error'):
            print('JS-ИСКЛЮЧЕНИЕ:', d['error'])
            bad += 1
        print('rows=%s panel=%s %s' % (d.get('rows'), d.get('panel'), d.get('domCounts')))
        if d.get('fetched') is not None:
            print('fetch:', d['fetched'])
            if sorted(x.rsplit('/', 1)[-1] for x in d['fetched']) != ['model_hltv.json', 'team_ratings.json']:
                print('ОШИБКА: ветка chrome.runtime.getURL не забрала оба файла бандла')
                bad += 1
        print(d.get('text') or '—')
        if d.get('kind') == 'unit':
            if d.get('failed'):
                bad += 1
            continue
        maps = (d.get('domCounts') or {}).get('infoboxMaps') or 0
        if not d.get('panel') or not d.get('rows') and maps:
            bad += 1
    print('=' * 70)
    print('ПРОБЛЕМ:', bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
