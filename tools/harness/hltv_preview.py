# -*- coding: utf-8 -*-
"""Маркетинговое превью HLTV-панели для скриншотов Chrome Web Store.

    python tools/harness/hltv_preview.py <фрагменты.json> <predict|live> <out.html>

В отличие от стендов, тут панель показана как продуктовый оверлей поверх
тёмного hero-блока, а разметка матча — реальные фрагменты, снятые живым
браузером (frag_server). content.js и styles.css подключаются по абсолютным
путям от корня проекта, поэтому превью надо отдавать через http.server и
пересобирать после любой правки расширения.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from hltv_stand import bundle_js, fixture_from_json  # noqa: E402

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>CS2 Pro Predictor (HLTV) — preview</title>
<link rel="stylesheet" href="/hltv_extension/styles.css">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; overflow: hidden; }
  body { background: #080b10; color: #e6edf3; font-family: "Segoe UI", Roboto, Arial, sans-serif; }
  body::before { content: ""; position: fixed; inset: 0; background:
    radial-gradient(820px 620px at 10% 8%, rgba(31,111,235,.20), transparent 62%),
    radial-gradient(900px 700px at 95% 92%, rgba(88,166,255,.12), transparent 64%),
    linear-gradient(160deg,#0b1016 0%,#0d1117 55%,#090c10 100%); }
  body::after { content: ""; position: fixed; inset: 0; background-image:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
    background-size: 56px 56px; mask-image: radial-gradient(circle at 30% 40%, #000 0%, transparent 72%); }
  .hero { position: relative; z-index: 1; display: flex; align-items: center; height: 100%; padding-left: 72px; }
  .left { width: 600px; }
  .brand { display: flex; align-items: center; gap: 13px; }
  .brand img { width: 46px; height: 46px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.45); }
  .brand-name { font-size: 15px; font-weight: 700; }
  .brand-name span { color: #58a6ff; }
  .badge { display: inline-block; margin-top: 30px; padding: 4px 10px; border: 1px solid rgba(88,166,255,.45);
    border-radius: 999px; color: #79b8ff; font-size: 10.5px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; }
  h1 { margin: 16px 0 18px; font-size: 50px; line-height: 1.04; letter-spacing: -1.6px; font-weight: 800; }
  h1 span { color: #58a6ff; }
  .lead { max-width: 560px; margin: 0 0 24px; color: #9aa7b4; font-size: 16.5px; line-height: 1.55; }
  ul { margin: 0; padding: 0; list-style: none; }
  li { margin: 11px 0; color: #c9d1d9; font-size: 14.5px; }
  li::before { content: "▸"; margin-right: 10px; color: #58a6ff; font-weight: 700; }
  .foot { position: fixed; left: 72px; bottom: 30px; color: #5b6673; font-size: 11px; }
  #hp-fixture { position: absolute; left: -9999px; top: 0; width: 900px; }
  #hltv-pro-panel { position: fixed !important; top: 32px; right: 40px; width: 480px;
    max-height: calc(100vh - 64px); overflow: hidden; margin: 0;
    box-shadow: 0 18px 50px rgba(0,0,0,.55); }
  @VIEWCSS@
</style></head>
<body>
  <div class="hero"><div class="left">
    <div class="brand"><img src="/hltv_extension/icon.png" alt="">
      <div class="brand-name">CS2 Pro Predictor <span>(HLTV)</span></div></div>
    <div class="badge">@BADGE@</div>
    <h1>@TITLE@</h1>
    <p class="lead">@LEAD@</p>
    <ul>@POINTS@</ul>
  </div></div>
  <div class="foot">Не связано с HLTV. Прогноз — оценка вероятности, не совет ставить.</div>
  <div id="hp-fixture">
@FIXTURE@
  </div>
  <script>window.__hltvForceMount = true; window.__hltvProBundle = @BUNDLE@;</script>
  <script src="/hltv_extension/content.js"></script>
</body></html>
"""

VIEWS = {
    'predict': {
        'badge': 'HLTV · UPCOMING MATCHES',
        'title': 'Прогноз на просцену<br><span>своей моделью</span>',
        'lead': 'CatBoost на 28 415 реальных матчах HLTV считает вероятность победы ещё до вето — без коэффициентов букмекеров.',
        'points': [
            'Вероятность серии подписана командой, вторая — дополнением',
            'Признаки: Elo, форма, отдых, активность за 30 дней',
            'Честные метрики на матчах, которых модель не видела',
            'Вето и винрейты по картам — рядом, но отдельно от прогноза',
        ],
        'css': '',
    },
    'live': {
        'badge': 'HLTV · LIVE RECALC',
        'title': 'Вероятность, которая<br><span>живёт вместе с матчем</span>',
        'lead': 'По ходу серии панель пересчитывает шанс победы по текущему счёту карты и счёту по картам — динамикой MR12, а не готовым числом HLTV.',
        'points': [
            'Текущая карта и счёт по картам читаются со страницы',
            'Овертаймы MR12 учтены, мульти-ОТ тоже',
            'Видно и предматчевую, и живую вероятность — для сравнения',
            'Стороны CT/T не путаются с порядком команд',
        ],
        'css': '#hltv-pro-panel > .hp-table, #hltv-pro-panel > .hp-rec, #hltv-pro-panel > .hp-note { display: none; }',
    },
}


def main():
    src, view, out = sys.argv[1], sys.argv[2], sys.argv[3]
    f = json.load(io.open(src, encoding='utf-8'))
    if isinstance(f, str):
        f = json.loads(f)
    fixture = f.get('fixture') or fixture_from_json(f)
    v = VIEWS[view]
    html = PAGE
    for token, value in (
        ('@BADGE@', v['badge']),
        ('@TITLE@', v['title']),
        ('@LEAD@', v['lead']),
        ('@POINTS@', ''.join('<li>%s</li>' % p for p in v['points'])),
        ('@VIEWCSS@', v['css']),
        ('@FIXTURE@', fixture),
        ('@BUNDLE@', bundle_js()),
    ):
        html = html.replace(token, value)
    io.open(out, 'w', encoding='utf-8').write(html)
    print('превью:', out, len(html), 'байт')


if __name__ == '__main__':
    main()