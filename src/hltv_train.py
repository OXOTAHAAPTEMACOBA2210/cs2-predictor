# -*- coding: utf-8 -*-
"""Обучение модели pro-матчей CS2 на реальном архиве результатов HLTV.

Выборка: data/hltv_results.tsv (35 204 матча, 2023-05-18..2026-11-08), собрана
коллектором со страниц /results. Признаки считаются строго хронологически
(только матчи ДО текущего), и только те, которые расширение сможет повторить
на странице матча без запросов: разница рейтингов Эло, форма, отдых, активность,
звёзды события и формат серии — всё из бандла team_ratings.json + DOM.

Запуск: C:\\ProgramData\\anaconda3\\python.exe src/hltv_train.py
"""
import json
import math
import os
from bisect import bisect_left
from collections import defaultdict

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV = os.path.join(ROOT, 'data', 'hltv_results.tsv')
TEST_FROM = '2026-08-01'
VAL_FROM = '2026-06-01'
MAP_CODES_BO1 = {'anc', 'cch', 'anb', 'inf', 'd2', 'nuke', 'mrg', 'ovp',
                 'trn', 'cbl', 'vtg', 'dust2', 'mirage', 'inferno',
                 'ancient', 'cache', 'anubis', 'vertigo', 'train', 'overpass'}
FEATURES = ['elo_diff', 'form5_diff', 'form10_diff', 'rest_diff', 'n30_diff',
            'log_n_diff', 'is_bo1', 'is_bo5']


def load_rows():
    df = pd.read_csv(TSV, sep='\t', header=None, names=['id', 'date', 't1', 't2',
                                                        's1', 's2', 'bo', 'stars'],
                     dtype={'id': str, 'date': str, 't1': str, 't2': str,
                            'bo': str, 'stars': int})
    df['s1'] = pd.to_numeric(df['s1'], errors='coerce')
    df['s2'] = pd.to_numeric(df['s2'], errors='coerce')
    df = df.dropna(subset=['s1', 's2'])
    df['bo'] = df['bo'].where(~df['bo'].isin(MAP_CODES_BO1), 'bo1')
    # «def» в колонке формата = технический результат (неявка), а не сыгранный
    # матч: в рейтинг и форму такие строки попадать не должны.
    df = df[df['bo'] != 'def']
    df = df[df['bo'].isin(['bo1', 'bo2', 'bo3', 'bo5'])]
    df = df[df['bo'] != 'bo2']
    df = df[df['s1'] != df['s2']]
    expect = {'bo1': 1, 'bo3': 2, 'bo5': 3}
    ok = [max(r.s1, r.s2) == expect[r.bo] and min(r.s1, r.s2) < expect[r.bo]
          for r in df.itertuples()]
    df = df[ok]
    df = df.sort_values(['date', 'id'], kind='mergesort').reset_index(drop=True)
    return df


class TeamState:
    __slots__ = ('elo', 'res', 'ords', 'last_str', 'n')

    def __init__(self):
        self.elo = 1000.0
        self.res = []
        self.ords = []
        self.last_str = None
        self.n = 0


def winrate(vals):
    return sum(vals) / len(vals) if vals else 0.5


def build_features(df):
    teams = defaultdict(TeamState)
    rows = []
    for r in df.itertuples():
        d = pd.Timestamp(r.date)
        d_ord = d.toordinal()
        a, b = teams[r.t1], teams[r.t2]
        rest_a = min(d_ord - a.ords[-1], 90) if a.ords else 30
        rest_b = min(d_ord - b.ords[-1], 90) if b.ords else 30
        n30_a = len(a.ords) - bisect_left(a.ords, d_ord - 30)
        n30_b = len(b.ords) - bisect_left(b.ords, d_ord - 30)
        rows.append({
            'date': r.date, 'id': r.id, 't1': r.t1, 't2': r.t2,
            's1': int(r.s1), 's2': int(r.s2), 'bo': r.bo, 'stars': r.stars,
            'elo_diff': a.elo - b.elo,
            'form5_diff': winrate(a.res[-5:]) - winrate(b.res[-5:]),
            'form10_diff': winrate(a.res[-10:]) - winrate(b.res[-10:]),
            'rest_diff': math.log1p(rest_a) - math.log1p(rest_b),
            'n30_diff': n30_a - n30_b,
            'log_n_diff': math.log1p(a.n) - math.log1p(b.n),
            'is_bo1': 1.0 if r.bo == 'bo1' else 0.0,
            'is_bo5': 1.0 if r.bo == 'bo5' else 0.0,
        })
        win_a = r.s1 > r.s2
        margin = abs(r.s1 - r.s2)
        mult = min(1.0 + 0.15 * (margin - 1), 1.3)
        k = 30.0 * mult
        ea = 1.0 / (1.0 + 10 ** ((b.elo - a.elo) / 400.0))
        a.elo += k * ((1.0 if win_a else 0.0) - ea)
        b.elo += k * ((0.0 if win_a else 1.0) - (1.0 - ea))
        for st, won in ((a, win_a), (b, not win_a)):
            st.res.append(1 if won else 0)
            st.ords.append(d_ord)
            st.last_str = r.date
            st.n += 1
    return pd.DataFrame(rows), teams


def main():
    df = load_rows()
    print('матчей после чистки:', len(df), df['date'].min(), '->', df['date'].max())
    feat, teams = build_features(df)
    y = (feat['s1'] > feat['s2']).astype(int).values
    X = feat[FEATURES].values.astype(float)

    tr = feat['date'] < VAL_FROM
    va = (feat['date'] >= VAL_FROM) & (feat['date'] < TEST_FROM)
    te = feat['date'] >= TEST_FROM
    print('train %d / val %d / test %d' % (tr.sum(), va.sum(), te.sum()))

    model = CatBoostClassifier(
        depth=5, learning_rate=0.05, l2_leaf_reg=5.0,
        loss_function='Logloss', eval_metric='Logloss',
        iterations=600, use_best_model=True, random_seed=7,
    )
    model.fit(X[tr.values], y[tr.values], eval_set=(X[va.values], y[va.values]),
              early_stopping_rounds=60, verbose=False)
    print('деревьев:', model.tree_count_)

    def report(name, p, yy):
        from sklearn.metrics import roc_auc_score, log_loss, accuracy_score
        pred = (p >= 0.5).astype(int)
        print('%-22s acc %.4f  auc %.4f  logloss %.4f  brier %.4f'
              % (name, accuracy_score(yy, pred), roc_auc_score(yy, p),
                 log_loss(yy, np.clip(p, 1e-6, 1 - 1e-6)), float(np.mean((p - yy) ** 2))))

    p_te = model.predict_proba(X[te.values])[:, 1]
    y_te = y[te.values]
    report('catboost (test)', p_te, y_te)
    elo = feat['elo_diff'].values[te.values]
    report('baseline elo>0 (test)', (1.0 / (1.0 + 10 ** (-elo / 400.0))), y_te)
    report('baseline always t1 (test)', np.full(len(y_te), 0.5), y_te)

    print('\nкалибровка на test (децили предсказания):')
    order = np.argsort(p_te)
    buckets = np.array_split(order, 10)
    for b in buckets:
        print('  P=%.2f  факт=%.2f  n=%d' % (p_te[b].mean(), y_te[b].mean(), len(b)))

    print('\nважность признаков:')
    for name, imp in sorted(zip(FEATURES, model.get_feature_importance()),
                            key=lambda x: -x[1]):
        print('  %-12s %5.1f%%' % (name, imp))

    stars = feat['stars'].values[te.values]
    tier = stars >= 1
    if tier.sum() > 200:
        report('catboost (test, stars>=1)', p_te[tier], y_te[tier])
        report('baseline elo (stars>=1)', 1.0 / (1.0 + 10 ** (-elo[tier] / 400.0)), y_te[tier])

    # экспорт: модель в том же json-формате, что читает расширение
    cbm = os.path.join(ROOT, 'models', 'catboost_hltv.cbm')
    model.save_model(cbm)
    cb_json = os.path.join(ROOT, 'hltv_extension', 'model_hltv.json')
    model.save_model(cb_json, format='json', export_parameters=None)
    m = json.load(open(cb_json, encoding='utf-8'))
    names = {i: n for i, n in enumerate(FEATURES)}
    for f in m['features_info']['float_features']:
        f['name'] = names.get(f['feature_index'], f['feature_index'])
        f['feature_id'] = f['name']
    m['features_info']['float_features'].sort(key=lambda f: f['feature_index'])
    json.dump(m, open(cb_json, 'w', encoding='utf-8'), ensure_ascii=False)
    print('\nмодель:', cb_json, 'деревьев', len(m['oblivious_trees']))

    ratings = {name: {'elo': round(st.elo, 1), 'n': st.n,
                      'last': st.last_str,
                      'f5': round(winrate(st.res[-5:]), 3),
                      'f10': round(winrate(st.res[-10:]), 3),
                      'n30': len(st.ords) - bisect_left(st.ords, st.ords[-1] - 30) if st.ords else 0}
               for name, st in teams.items()}
    # метрики уезжают в тот же файл: панель расширения показывает их как есть,
    # без хардкода чисел в content.js
    from sklearn.metrics import roc_auc_score, accuracy_score
    meta = {
        'matches': int(len(df)),
        'trees': int(model.tree_count_),
        'features': FEATURES,
        'train_from': str(df['date'].min()),
        'test_from': TEST_FROM,
        'test_n': int(te.sum()),
        'test_acc': round(float(accuracy_score(y_te, (p_te >= 0.5).astype(int))), 4),
        'test_auc': round(float(roc_auc_score(y_te, p_te)), 4),
        'test_brier': round(float(np.mean((p_te - y_te) ** 2)), 4),
        'first_team_acc': round(float(np.mean(y_te)), 4),
    }
    rp = os.path.join(ROOT, 'hltv_extension', 'team_ratings.json')
    json.dump({'as_of': df['date'].max(), 'meta': meta, 'teams': ratings},
              open(rp, 'w', encoding='utf-8'), ensure_ascii=False)
    print('рейтинги:', rp, 'команд', len(ratings), 'meta', meta)

    probe = feat[te.values].head(3)
    for _, r in probe.iterrows():
        x = np.array([[r[f] for f in FEATURES]], dtype=float)
        print('probe', r['date'], r['t1'], 'vs', r['t2'], 'P=%.3f' % model.predict_proba(x)[0, 1])


if __name__ == '__main__':
    main()
