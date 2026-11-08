# -*- coding: utf-8 -*-
"""
Генерация графика для подраздела 3.5: Практическая апробация модели на реальном профиле FACEIT (-J0ker)
"""

import os
import matplotlib.pyplot as plt
import numpy as np

# Стилизация графиков
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10
plt.rcParams['figure.autolayout'] = True

maps = ['de_anubis', 'de_ancient', 'de_dust2', 'de_mirage', 'de_inferno', 'de_nuke', 'de_vertigo']
display_maps = ['Anubis', 'Ancient', 'Dust II', 'Mirage', 'Inferno', 'Nuke', 'Vertigo']
historical_wr = [56.20, 49.50, 48.72, 47.01, 42.03, 40.96, 25.00]
matches_played = [121, 101, 195, 268, 69, 83, 4]
solo_p_win = [52.81, 51.52, 51.23, 51.32, 47.35, 47.38, 46.88]
duo_p_win = [59.50, 58.20, 58.00, 58.10, 55.60, 55.70, 55.36]

x = np.arange(len(display_maps))
width = 0.35

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), dpi=300)

# График 1: Исторический винрейт и количество матчей игрока -J0ker
colors = ['#27ae60' if wr >= 50 else '#e67e22' if wr >= 45 else '#c0392b' for wr in historical_wr]
bars1 = ax1.bar(x, historical_wr, color=colors, width=0.55, edgecolor='black', linewidth=0.8, alpha=0.85)
ax1.axhline(50, color='gray', linestyle='--', linewidth=1.2, label='Баланс 50% Winrate')
ax1.set_xticks(x)
ax1.set_xticklabels(display_maps, fontweight='bold')
ax1.set_ylabel('Исторический винрейт игрока (%)', fontsize=11)
ax1.set_title('Историческая результативность игрока -J0ker\n(868 матчей, 4 LVL FACEIT)', fontsize=12, pad=12)
ax1.set_ylim(0, 70)
ax1.legend(loc='upper right')

for bar, m_count in zip(bars1, matches_played):
    height = bar.get_height()
    ax1.annotate(f'{height:.1f}%\n({m_count} игр)',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4), textcoords="offset points",
                ha='center', va='bottom', fontsize=8.5, fontweight='bold')

# График 2: Модельный предиктивный прогноз вероятности победы (CatBoost)
ax2.plot(display_maps, solo_p_win, marker='o', linewidth=2.5, color='#2980b9', label='Solo Queue (Соло-поиск)', markersize=7)
ax2.plot(display_maps, duo_p_win, marker='s', linewidth=2.5, color='#27ae60', linestyle='--', label='Duo Queue (с партнером K/D 1.15)', markersize=7)
ax2.axhline(50, color='gray', linestyle=':', linewidth=1.2, label='Порог безубыточности (50%)')

ax2.set_ylabel('Прогнозируемая моделью вероятность победы P(Win) (%)', fontsize=11)
ax2.set_title('Предиктивный прогноз исхода матча моделью CatBoost\nв зависимости от карты и формата лобби', fontsize=12, pad=12)
ax2.set_ylim(40, 65)
ax2.legend(loc='lower left')

for i, txt in enumerate(solo_p_win):
    ax2.annotate(f'{txt:.1f}%', (x[i], solo_p_win[i]), xytext=(0, -16), textcoords="offset points",
                 ha='center', fontsize=8.5, color='#1f618d', fontweight='bold')

for i, txt in enumerate(duo_p_win):
    ax2.annotate(f'{txt:.1f}%', (x[i], duo_p_win[i]), xytext=(0, 7), textcoords="offset points",
                 ha='center', fontsize=8.5, color='#1e8449', fontweight='bold')

plt.tight_layout()

# Сохранение в обе директории
out_latex = os.path.join(r"c:\Users\mrspa\Downloads\антигравити\faceit_ml_project\latex\figures\case_study_profile.png")
out_project = os.path.join(r"c:\Users\mrspa\Downloads\антигравити\faceit_ml_project\figures\case_study_profile.png")

fig.savefig(out_latex)
fig.savefig(out_project)
plt.close()

print(f"[УСПЕХ] График практической апробации сохранен в:\n - {out_latex}\n - {out_project}")
