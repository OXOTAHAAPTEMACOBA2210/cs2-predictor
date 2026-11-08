# -*- coding: utf-8 -*-
"""Офлайн-стенд для HLTV-панели.

Страница HLTV целиком гидратируется своим JS, поэтому сохранённый HTML как
стенд не годится. Работаем с фрагментами разметки: живым браузером
(browser-use -> evaluate_script) выгружаются outerHTML нужных блоков, из них
лепится страница, вживляется текущий hltv_extension/content.js и печатается
отчёт #hp-report.

    python tools/harness/hltv_stand.py <фрагменты.json> [имя]
    python tools/harness/hltv_stand.py --from-stand <готовый_стенд.html> [имя]

Фрагменты (ключи JSON): title, url, time, veto, infobox, sim, info, teamLinks
либо уже собранный fixture. --from-stand переиспользует разметку существующего
стенда, подставляя в неё свежий content.js — режим для повторных прогонов.

Далее: chrome --headless=new --allow-file-access-from-files --dump-dom <стенд>
и забрать блок <pre id="hp-report">.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT_DIR = os.path.join(HERE, 'hltv')
FIXTURES = os.path.join(OUT_DIR, 'fixtures')
EXT = os.path.join(ROOT, 'hltv_extension')

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>@TITLE@</title>
<link rel="stylesheet" href="@CSS@"></head>
<body>
<div id="hp-fixture">
@FIXTURE@
</div>
<script>window.__hltvForceMount = true;
window.__hltvProBundle = @BUNDLE@;
window.addEventListener('error', function (e) { window.__hpError = e.message + ' @' + e.lineno; });</script>
<script>
@LIB@
</script>
<script>
setTimeout(function () {
  var p = document.getElementById('hltv-pro-panel');
  var out = document.createElement('pre'); out.id = 'hp-report'; document.body.appendChild(out);
  var m = window.__hltvExtractProMatch ? window.__hltvExtractProMatch(document) : null;
  var all = function (sel, fn) { return p ? [].map.call(p.querySelectorAll(sel), fn) : []; };
  out.textContent = 'HP_STAND ' + JSON.stringify({
    loaded: !!window.__hltvProLoaded,
    error: window.__hpError || null,
    domCounts: {
      infoboxMaps: document.querySelectorAll('.map-stats-infobox-maps').length,
      vetoLines: document.querySelectorAll('.veto-box:not(.simulated-veto) .padding div').length,
      infobox: document.querySelectorAll('.map-stats-infobox').length,
      simSteps: document.querySelectorAll('.simulated-veto-step').length,
      mapholders: document.querySelectorAll('.mapholder:not(.simulated-map)').length,
      scorebot: document.querySelectorAll('.scorebot .score.scoreText').length
    },
    panel: !!p, text: p ? p.innerText : null,
    rows: p ? p.querySelectorAll('.hp-table tbody tr').length : 0,
    pred: {
      blocks: all('.hp-pred', function (e) { return 1; }).length,
      live: all('.hp-live', function (e) { return 1; }).length,
      nums: all('.hp-pred-num', function (e) { return e.textContent.trim(); }),
      heads: all('.hp-pred-head span:first-child', function (e) { return e.textContent.trim(); }),
      feats: all('.hp-f', function (e) { return e.textContent.replace(/\\s+/g, ' ').trim(); }),
      low: all('.hp-pred.hp-low', function (e) { return e.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200); })
    },
    start: m ? m.start : null,
    series: m ? m.series : null,
    extract: m
  }, null, 1);
}, 400);
</script>
</body></html>
"""

FIXTURE_RE = re.compile(r'<div id="hp-fixture">\n(.*?)\n</div>\n<script>window\.__hltvForceMount', re.S)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)

# Стенд-проверка live-динамики: те же функции, что считает панель на реальном
# матче, прогоняются на граничных счётах и сверяются с биномиальной формулой.
DP_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>HLTV DP unit</title></head>
<body>
<div id="hp-fixture"></div>
<script>window.__hltvProBundle = @BUNDLE@;
window.addEventListener('error', function (e) { window.__hpError = e.message + ' @' + e.lineno; });</script>
<script>
@LIB@
</script>
<script>
setTimeout(function () {
  var dp = window.__hltvProDP || {};
  var fails = [];
  var checks = 0;
  function near(name, got, want, eps) {
    checks++;
    if (!(typeof got === 'number') || Math.abs(got - want) > (eps || 1e-9)) {
      fails.push(name + ': ' + got + ' != ' + want);
    }
  }
  function ok(name, cond) { checks++; if (!cond) fails.push(name); }
  if (!dp.mapWinProb) fails.push('нет window.__hltvProDP');
  else {
    var ps = [0.3, 0.42, 0.5, 0.57, 0.7];
    var bos = [1, 3, 5];
    for (var i = 0; i < ps.length; i++) {
      for (var j = 0; j < bos.length; j++) {
        var p = ps[i], bo = bos[j];
        near('invert p=' + p + ' bo=' + bo, dp.invertSeries(dp.seriesFromMap(p, bo), bo), p);
        if (bo > 1) {
          near('series==DP p=' + p + ' bo=' + bo,
            dp.seriesWinProb(0, 0, Math.ceil(bo / 2), p, p), dp.seriesFromMap(p, bo), 1e-9);
        }
      }
    }
    near('seriesFromMap(0.5,3)', dp.seriesFromMap(0.5, 3), 0.5);
    near('seriesFromMap(0.6,3)', dp.seriesFromMap(0.6, 3), 0.648);
    near('map 0:0 p=0.5', dp.mapWinProb(0, 0, 0.5), 0.5, 1e-9);
    near('map 12:12 p=0.5', dp.mapWinProb(12, 12, 0.5), 0.5, 1e-9);
    near('map 15:15 p=0.5', dp.mapWinProb(15, 15, 0.5), 0.5, 1e-9);
    near('map 13:11', dp.mapWinProb(13, 11, 0.5), 1);
    near('map 11:13', dp.mapWinProb(11, 13, 0.5), 0);
    near('map 18:16 (2-й ОТ)', dp.mapWinProb(18, 16, 0.5), 1);
    near('map 16:18 (2-й ОТ)', dp.mapWinProb(16, 18, 0.5), 0);
    near('симметрия p=0.55', dp.mapWinProb(0, 0, 0.55) + dp.mapWinProb(0, 0, 0.45), 1, 1e-9);
    ok('p=0.55 даёт больше 0.5', dp.mapWinProb(0, 0, 0.55) > 0.5);
    ok('p=0.55 усиливается на дистанции', dp.mapWinProb(0, 0, 0.55) > 0.55);
    near('BO1 серия = карта', dp.seriesWinProb(0, 0, 1, 0.31, 0.9), 0.31);
    near('1:1 в BO3 = текущая карта', dp.seriesWinProb(1, 1, 2, 0.31, 0.9), 0.31);
    near('1:0 в BO3', dp.seriesWinProb(1, 0, 2, 0.6, 0.6), 0.6 + 0.4 * 0.6);
    var mono = true, bounds = true;
    for (var a = 0; a <= 20; a++) {
      for (var b = 0; b <= 20; b++) {
        var v = dp.mapWinProb(a, b, 0.52);
        if (!(v >= 0 && v <= 1)) bounds = false;
        if (a < 13 && dp.mapWinProb(a + 1, b, 0.52) < v - 1e-12) mono = false;
        if (b < 13 && dp.mapWinProb(a, b + 1, 0.52) > v + 1e-12) mono = false;
      }
    }
    checks += 2;
    ok('границы 0..1 на всех счётах', bounds);
    ok('счёт монотонен', mono);
  }
  var out = document.createElement('pre'); out.id = 'hp-report'; document.body.appendChild(out);
  out.textContent = 'HP_STAND ' + JSON.stringify({
    kind: 'unit',
    loaded: !!window.__hltvProLoaded,
    error: window.__hpError || null,
    failed: fails.length,
    text: 'проверок: ' + checks + ', провалов: ' + fails.length
      + (fails.length ? '\\n' + fails.join('\\n') : ''),
    panel: true, rows: 1
  }, null, 1);
}, 300);
</script>
</body></html>
"""


def build_dp():
    lib = io.open(os.path.join(EXT, 'content.js'), encoding='utf-8').read()
    html = DP_PAGE.replace('@BUNDLE@', bundle_js()).replace('@LIB@', lib)
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    out = os.path.join(OUT_DIR, 'dp-unit.html')
    io.open(out, 'w', encoding='utf-8').write(html)
    return out, len(html)


# Ветка загрузки через chrome.runtime.getURL + fetch в стендах не исполняется
# (там бандл подкладывается готовым), поэтому для неё есть отдельный стенд:
# chrome.runtime и fetch заглушены, а файлы отдаются из той же пары json.
STUB = """window.chrome = { runtime: { getURL: function (p) { return 'chrome-extension://hptest/' + p; } } };
window.__hpFiles = @FILES@;
window.__hpFetched = [];
window.fetch = function (url) {
  window.__hpFetched.push(url);
  return Promise.resolve({ json: function () { return Promise.resolve(window.__hpFiles[url]); } });
};"""


def build_fetch(fixture, title, name):
    lib = io.open(os.path.join(EXT, 'content.js'), encoding='utf-8').read()
    model = json.load(io.open(os.path.join(EXT, 'model_hltv.json'), encoding='utf-8'))
    ratings = json.load(io.open(os.path.join(EXT, 'team_ratings.json'), encoding='utf-8'))
    files = json.dumps({'chrome-extension://hptest/model_hltv.json': model,
                        'chrome-extension://hptest/team_ratings.json': ratings},
                       ensure_ascii=False, separators=(',', ':'))
    page = PAGE.replace('window.__hltvProBundle = @BUNDLE@;', STUB)
    page = page.replace("'HP_STAND ' + JSON.stringify({",
                        "'HP_STAND ' + JSON.stringify({\n    fetched: window.__hpFetched || [],")
    html = page
    for token, value in (
        ('@TITLE@', title),
        ('@CSS@', rel(os.path.join(EXT, 'styles.css'))),
        ('@FIXTURE@', fixture),
        ('@FILES@', files),
        ('@LIB@', lib),
    ):
        html = html.replace(token, value)
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    out = os.path.join(OUT_DIR, '%s.html' % re.sub(r'\.(json|html)$', '', name))
    io.open(out, 'w', encoding='utf-8').write(html)
    return out, len(html)


def rel(path):
    return os.path.relpath(path, OUT_DIR).replace('\\', '/')


def bundle_js():
    """Стенды живут на file:// без chrome.runtime, поэтому бандл модели
    подкладывается в страницу тем же объектом, который ждёт content.js."""
    model = json.load(io.open(os.path.join(EXT, 'model_hltv.json'), encoding='utf-8'))
    ratings = json.load(io.open(os.path.join(EXT, 'team_ratings.json'), encoding='utf-8'))
    return json.dumps({'model': model, 'asOf': ratings['as_of'],
                       'teams': ratings['teams'], 'meta': ratings.get('meta')},
                      ensure_ascii=False, separators=(',', ':'))


def fixture_from_json(f):
    links = ''.join('<a href="%s">%s</a>' % (l['href'], l['t']) for l in (f.get('teamLinks') or []))
    return '\n'.join(x for x in (
        '<div class="matchTime">%s</div>' % (f.get('time') or ''),
        f.get('teamsBox'), f.get('veto'), f.get('infobox'), f.get('sim'), f.get('info'),
        f.get('mapholders'), f.get('scorebot'), links) if x)


def build(fixture, title, name):
    lib = io.open(os.path.join(EXT, 'content.js'), encoding='utf-8').read()
    html = PAGE
    for token, value in (
        ('@TITLE@', title),
        ('@CSS@', rel(os.path.join(EXT, 'styles.css'))),
        ('@FIXTURE@', fixture),
        ('@BUNDLE@', bundle_js()),
        ('@LIB@', lib),
    ):
        html = html.replace(token, value)
    for d in (OUT_DIR, FIXTURES):
        if not os.path.isdir(d):
            os.makedirs(d)
    name = re.sub(r'\.(json|html)$', '', name)
    io.open(os.path.join(FIXTURES, '%s.json' % name), 'w', encoding='utf-8').write(
        json.dumps({'title': title, 'fixture': fixture}, ensure_ascii=False, indent=1))
    out = os.path.join(OUT_DIR, '%s.html' % name)
    io.open(out, 'w', encoding='utf-8').write(html)
    return out, len(html)


def main():
    src = sys.argv[1]
    if src == '--dp':
        return build_dp()
    if src == '--fetch':
        f = json.load(io.open(sys.argv[2], encoding='utf-8'))
        if isinstance(f, str):
            f = json.loads(f)
        fixture = f.get('fixture') or fixture_from_json(f)
        name = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(sys.argv[2])
        return build_fetch(fixture, f.get('title') or 'HLTV match', name)
    if src == '--from-stand':
        html = io.open(sys.argv[2], encoding='utf-8').read()
        m = FIXTURE_RE.search(html)
        if not m:
            raise SystemExit('в стенде нет блока #hp-fixture — собери его заново из фрагментов')
        t = TITLE_RE.search(html)
        name = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(sys.argv[2])
        return build(m.group(1), t.group(1) if t else 'HLTV match', name)
    f = json.load(io.open(src, encoding='utf-8'))
    if isinstance(f, str):          # evaluate_script пишет результат как JSON-строку
        f = json.loads(f)
    fixture = f.get('fixture') or fixture_from_json(f)
    name = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(src)
    return build(fixture, f.get('title') or 'HLTV match', name)


if __name__ == '__main__':
    path, size = main()
    print('стенд:', path, size, 'байт')
