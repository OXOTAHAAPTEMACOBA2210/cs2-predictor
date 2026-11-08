# -*- coding: utf-8 -*-
import json

nb_path = r"c:\Users\mrspa\Downloads\антигравити\faceit_ml_project\notebooks\faceit_coursework.ipynb"
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

case_md = {
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## **4. Практическая апробация: Предиктивный анализ соревновательного профиля (-J0ker)**\n",
        "\n",
        "Проверка обученной модели CatBoost на реальных соревновательных данных игрока FACEIT:\n",
        "- **Никнейм:** `-J0ker` (в игре: `V L A D O S _ R O Y C E`)\n",
        "- **Дивизион:** 4 LVL (987 ELO), 868 сыгранных матчей (415 побед, винрейт 47.81%)\n",
        "- **Индивидуальные метрики:** K/D 0.93, ADR 76.53, HS% 40.0%\n",
        "\n",
        "Модель прогнозирует вероятность победы в зависимости от выбора карты и состава лобби (соло vs дуо)."
    ]
}

case_code = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "# Анализ вероятности победы для профиля -J0ker\n",
        "maps = ['de_anubis', 'de_ancient', 'de_dust2', 'de_mirage', 'de_inferno', 'de_nuke', 'de_vertigo']\n",
        "display_maps = ['Anubis', 'Ancient', 'Dust II', 'Mirage', 'Inferno', 'Nuke', 'Vertigo']\n",
        "map_wrs = {'de_anubis': 56.20, 'de_ancient': 49.50, 'de_dust2': 48.72, 'de_mirage': 47.01, 'de_inferno': 42.03, 'de_nuke': 40.96, 'de_vertigo': 25.00}\n",
        "\n",
        "solo_preds = []\n",
        "duo_preds = []\n",
        "\n",
        "for m in maps:\n",
        "    # 1. Solo Queue (случайные тиммейты ~990 ELO)\n",
        "    row_solo = {c: 0.0 for c in feature_cols}\n",
        "    team1_elo = 989.4\n",
        "    team2_elo = 990.0\n",
        "    team1_kd = 0.97\n",
        "    team2_kd = 0.98\n",
        "    team1_adr = 76.1\n",
        "    team2_adr = 76.0\n",
        "    team1_hs = 41.6\n",
        "    team2_hs = 42.0\n",
        "    team1_mwr = (map_wrs[m] + 4 * 50.0) / 5.0\n",
        "    \n",
        "    row_solo['team_1_avg_elo'] = team1_elo\n",
        "    row_solo['team_2_avg_elo'] = team2_elo\n",
        "    row_solo['elo_diff'] = team1_elo - team2_elo\n",
        "    row_solo['team_1_elo_std'] = 80.0\n",
        "    row_solo['team_2_elo_std'] = 80.0\n",
        "    row_solo['elo_std_diff'] = 0.0\n",
        "    row_solo['team_1_avg_kd'] = team1_kd\n",
        "    row_solo['team_2_avg_kd'] = team2_kd\n",
        "    row_solo['kd_diff'] = team1_kd - team2_kd\n",
        "    row_solo['team_1_avg_adr'] = team1_adr\n",
        "    row_solo['team_2_avg_adr'] = team2_adr\n",
        "    row_solo['adr_diff'] = team1_adr - team2_adr\n",
        "    row_solo['team_1_hs_rate'] = team1_hs\n",
        "    row_solo['team_2_hs_rate'] = team2_hs\n",
        "    row_solo['hs_diff'] = team1_hs - team2_hs\n",
        "    row_solo['team_1_map_winrate'] = team1_mwr\n",
        "    row_solo['team_2_map_winrate'] = 50.0\n",
        "    row_solo['map_winrate_diff'] = team1_mwr - 50.0\n",
        "    row_solo['team_1_streak'] = 0.0\n",
        "    row_solo['team_2_streak'] = 0.0\n",
        "    row_solo['streak_diff'] = 0.0\n",
        "    row_solo['team_1_avg_matches'] = (868 + 4 * 700) / 5.0\n",
        "    row_solo['team_2_avg_matches'] = 700.0\n",
        "    if f'map_name_{m}' in row_solo:\n",
        "        row_solo[f'map_name_{m}'] = 1.0\n",
        "        \n",
        "    p_solo = models['CatBoost Classifier'].predict_proba(pd.DataFrame([row_solo]))[0, 1]\n",
        "    solo_preds.append(p_solo * 100)\n",
        "    \n",
        "    # 2. Duo Queue (Владислав + сильный напарник KD 1.15, ELO 1050)\n",
        "    row_duo = row_solo.copy()\n",
        "    row_duo['team_1_avg_elo'] = 1001.4\n",
        "    row_duo['elo_diff'] = 11.4\n",
        "    row_duo['team_1_avg_kd'] = 1.004\n",
        "    row_duo['kd_diff'] = 0.024\n",
        "    row_duo['team_1_avg_adr'] = 77.8\n",
        "    row_duo['adr_diff'] = 1.8\n",
        "    row_duo['team_1_map_winrate'] = (map_wrs[m] + 55.0 + 3 * 50.0) / 5.0\n",
        "    row_duo['map_winrate_diff'] = row_duo['team_1_map_winrate'] - 50.0\n",
        "    \n",
        "    p_duo = models['CatBoost Classifier'].predict_proba(pd.DataFrame([row_duo]))[0, 1]\n",
        "    duo_preds.append(p_duo * 100)\n",
        "\n",
        "res_df = pd.DataFrame({\n",
        "    'Карта': display_maps,\n",
        "    'Винрейт игрока (%)': [map_wrs[m] for m in maps],\n",
        "    'P(Win) Solo Queue (%)': [round(x, 2) for x in solo_preds],\n",
        "    'P(Win) Duo Queue (%)': [round(x, 2) for x in duo_preds]\n",
        "})\n",
        "res_df\n"
    ]
}

if len(nb["cells"]) <= 7:
    nb["cells"].extend([case_md, case_code])
    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=2)
    print("Notebook updated successfully with case study cells!")
else:
    print(f"Notebook already has {len(nb['cells'])} cells.")
