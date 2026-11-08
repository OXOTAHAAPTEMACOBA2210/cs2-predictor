# -*- coding: utf-8 -*-
"""Записывает ответы FACEIT API для комнаты в fixtures/index.json.

Стенд (harness.js) отдаёт content.js ровно эти ответы, поэтому панель можно
прогонять офлайн и без нагрузки на API.

    python tools/harness/capture.py 1-3fa76ab6-f853-44fc-b97f-5d3313800e59
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, 'fixtures')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def api(path):
    req = urllib.request.Request('https://www.faceit.com/api' + path,
                                 headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as exc:
            code = getattr(exc, 'code', None)
            if code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(8 * (attempt + 1))
                continue
            raise


def main():
    match_id = sys.argv[1]
    out = {}
    room = api('/match/v2/match/%s' % match_id)
    out['/match/v2/match/%s' % match_id] = room
    teams = (room.get('payload') or {}).get('teams') or {}
    players = []
    for t in teams.values():
        players.extend((t.get('roster') or []))
    print('игроков:', len(players))
    for p in players:
        pid = p['id']
        out['/stats/v1/stats/users/%s/games/cs2' % pid] = api(
            '/stats/v1/stats/users/%s/games/cs2' % pid)
        time.sleep(1.0)
        out['/stats/v1/stats/time/users/%s/games/cs2?size=50&page=0' % pid] = api(
            '/stats/v1/stats/time/users/%s/games/cs2?size=50&page=0' % pid)
        time.sleep(1.0)
        if p.get('elo') is None:
            out['/users/v1/users/%s' % pid] = api('/users/v1/users/%s' % pid)
            time.sleep(1.0)
    if not os.path.isdir(FIXTURES):
        os.makedirs(FIXTURES)
    path = os.path.join(FIXTURES, 'match-%s.json' % match_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print('записано:', path, len(out), 'ответов')


if __name__ == '__main__':
    main()
