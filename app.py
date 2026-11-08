# -*- coding: utf-8 -*-
"""
FACEIT Scout & AI Predictor (CS2)
1. Автоматический парсинг матча FACEIT по ссылке в один клик
2. Оценка вероятности победы и рекомендация доджа (Dodge Advisor)
3. Поиск валуйных ставок для букмекеров (Value Betting)
"""

import os
import sys
import pandas as pd
import streamlit as st
from catboost import CatBoostClassifier

# Добавляем путь к модулям
sys.path.append(os.path.dirname(__file__))
from src.match_fetcher import fetch_match_details

st.set_page_config(
    page_title="FACEIT Match Scout & AI Predictor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #1a1e29; padding: 15px; border-radius: 10px; border: 1px solid #2d3748; }
    .verdict-play { background: linear-gradient(135deg, #1e7e34, #28a745); padding: 18px; border-radius: 12px; color: white; font-weight: bold; text-align: center; font-size: 24px; box-shadow: 0 4px 15px rgba(40,167,69,0.3); }
    .verdict-neutral { background: linear-gradient(135deg, #d39e00, #ffc107); padding: 18px; border-radius: 12px; color: #212529; font-weight: bold; text-align: center; font-size: 24px; box-shadow: 0 4px 15px rgba(255,193,7,0.3); }
    .verdict-weak { background: linear-gradient(135deg, #495057, #6c757d); padding: 18px; border-radius: 12px; color: white; font-weight: bold; text-align: center; font-size: 24px; box-shadow: 0 4px 15px rgba(108,117,125,0.3); }
    .match-box { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# Загрузка обученной модели CatBoost
@st.cache_resource
def load_ml_model():
    model_path = os.path.join(os.path.dirname(__file__), "models", "catboost_faceit.cbm")
    if not os.path.exists(model_path):
        data_path = os.path.join(os.path.dirname(__file__), "data", "faceit_matches.csv")
        df = pd.read_csv(data_path)
        df_enc = pd.get_dummies(df, columns=['map_name'], drop_first=True)
        feature_cols = [c for c in df_enc.columns if c not in ['match_id', 'team_1_win']]
        model = CatBoostClassifier(iterations=400, learning_rate=0.05, depth=6, verbose=0, random_seed=42)
        model.fit(df_enc[feature_cols], df_enc['team_1_win'])
        os.makedirs(os.path.join(os.path.dirname(__file__), "models"), exist_ok=True)
        model.save_model(model_path)
    else:
        model = CatBoostClassifier()
        model.load_model(model_path)
    
    feature_cols = [
        'team_1_avg_elo', 'team_2_avg_elo', 'elo_diff', 'team_1_elo_std', 'team_2_elo_std', 'elo_std_diff',
        'team_1_avg_kd', 'team_2_avg_kd', 'kd_diff', 'team_1_avg_adr', 'team_2_avg_adr', 'adr_diff',
        'team_1_hs_rate', 'team_2_hs_rate', 'hs_diff', 'team_1_map_winrate', 'team_2_map_winrate', 'map_winrate_diff',
        'team_1_streak', 'team_2_streak', 'streak_diff', 'team_1_avg_matches', 'team_2_avg_matches',
        'map_name_de_anubis', 'map_name_de_dust2', 'map_name_de_inferno', 'map_name_de_mirage', 'map_name_de_nuke', 'map_name_de_vertigo'
    ]
    return model, feature_cols

model, feature_cols = load_ml_model()

def predict_match(t1_elo, t2_elo, t1_kd, t2_kd, t1_adr, t2_adr, t1_hs, t2_hs,
                  t1_mwr, t2_mwr, t1_std, t2_std, t1_streak, t2_streak,
                  t1_matches, t2_matches, map_name):
    row = {c: 0.0 for c in feature_cols}
    row['team_1_avg_elo'] = t1_elo
    row['team_2_avg_elo'] = t2_elo
    row['elo_diff'] = t1_elo - t2_elo
    row['team_1_elo_std'] = t1_std
    row['team_2_elo_std'] = t2_std
    row['elo_std_diff'] = t1_std - t2_std
    row['team_1_avg_kd'] = t1_kd
    row['team_2_avg_kd'] = t2_kd
    row['kd_diff'] = t1_kd - t2_kd
    row['team_1_avg_adr'] = t1_adr
    row['team_2_avg_adr'] = t2_adr
    row['adr_diff'] = t1_adr - t2_adr
    row['team_1_hs_rate'] = t1_hs
    row['team_2_hs_rate'] = t2_hs
    row['hs_diff'] = t1_hs - t2_hs
    row['team_1_map_winrate'] = t1_mwr
    row['team_2_map_winrate'] = t2_mwr
    row['map_winrate_diff'] = t1_mwr - t2_mwr
    row['team_1_streak'] = t1_streak
    row['team_2_streak'] = t2_streak
    row['streak_diff'] = t1_streak - t2_streak
    row['team_1_avg_matches'] = t1_matches
    row['team_2_avg_matches'] = t2_matches
    
    dummy = f"map_name_{map_name}"
    if dummy in row:
        row[dummy] = 1.0
        
    df_row = pd.DataFrame([row])
    return model.predict_proba(df_row)[0, 1]

# ------------------------------------------------------------------------------
# ГЛАВНЫЙ ЭКРАН
# ------------------------------------------------------------------------------
st.title("🎯 FACEIT Instant Match Scout & AI Predictor")
st.markdown("Вставь ссылку на комнату матча FACEIT — система за 2 секунды выгрузит 10 игроков, оценит баланс сил и выдаст вердикт: **ИГРАТЬ или НЕЙТРАЛЬНО**.")

# Поле для вставки ссылки
default_demo_url = "https://www.faceit.com/en/cs2/room/1-2ab7b581-fa02-4153-93ee-179755f25042"
user_url = st.text_input("🔗 Ссылка на комнату матча FACEIT (Match Room URL):", value=default_demo_url)

col_btn1, col_btn2 = st.columns([1, 4])
with col_btn1:
    btn_analyze = st.button("⚡ АНАЛИЗИРОВАТЬ МАТЧ", type="primary")

match_data = None
if btn_analyze or 'match_cache' not in st.session_state:
    if user_url:
        with st.spinner("🔄 Подключение к FACEIT API и выгрузка статистики 10 игроков..."):
            try:
                match_data = fetch_match_details(user_url)
                st.session_state['match_cache'] = match_data
            except Exception as e:
                st.error(f"Ошибка загрузки матча: {e}")
    else:
        st.warning("Вставьте ссылку на матч!")
else:
    match_data = st.session_state.get('match_cache')

if match_data:
    t1 = match_data['team_1']
    t2 = match_data['team_2']
    cur_map = match_data['map']
    
    # Расчет вероятности победы
    prob_t1 = predict_match(
        t1['avg_elo'], t2['avg_elo'],
        t1['avg_kd'], t2['avg_kd'],
        t1['avg_adr'], t2['avg_adr'],
        t1['hs'], t2['hs'],
        t1['map_wr'], t2['map_wr'],
        t1['elo_std'], t2['elo_std'],
        t1['streak'], t2['streak'],
        t1['avg_matches'], t2['avg_matches'],
        cur_map
    )
    prob_pct = prob_t1 * 100.0
    
    st.markdown("---")
    st.subheader(f"🏟️ Матч `{match_data['match_id']}` | Карта: **`{cur_map}`**")
    
    # Вердикт
    v_col1, v_col2, v_col3 = st.columns([1, 1.4, 1])
    with v_col1:
        st.metric(f"Шанс на победу {t1['name']}", f"{prob_pct:.1f}%")
        st.metric(f"Шанс на победу {t2['name']}", f"{100 - prob_pct:.1f}%")
        
    with v_col2:
        if prob_pct >= 55.0:
            st.markdown('<div class="verdict-play">✅ РЕКОМЕНДАЦИЯ: ИГРАТЬ!<br><span style="font-size:15px; font-weight:normal;">Положительное матожидание. Перевес твоей команды по статистике.</span></div>', unsafe_allow_html=True)
        elif prob_pct >= 46.5:
            st.markdown('<div class="verdict-neutral">⚖️ НЕЙТРАЛЬНЫЙ МАТЧ<br><span style="font-size:15px; font-weight:normal;">Примерно равные составы. Исход решат стартовые раунды.</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="verdict-weak">⚖️ НИЖЕ СРЕДНЕГО, НО НЕ СИГНАЛ К ДОДЖУ<br><span style="font-size:15px; font-weight:normal;">По бэктесту на реальных матчах комнаты с такой вероятностью выигрывались примерно в половине случаев, поэтому рекомендация «доджить» убрана.</span></div>', unsafe_allow_html=True)
            
    with v_col3:
        st.metric("Разница среднего K/D (ΔKD)", f"{t1['avg_kd'] - t2['avg_kd']:+.2f}")
        st.metric("Разница среднего ELO (ΔELO)", f"{t1['avg_elo'] - t2['avg_elo']:+d}")

    # Детектор СМУРФОВ и РУИНЕРОВ (Threat Intelligence)
    alerts = match_data.get('alerts', [])
    if alerts:
        st.markdown("---")
        st.markdown("### ⚠️ Обнаруженные угрозы матча (Смурфы и Руинеры)")
        for a in alerts:
            if a['type'] == 'DANGER':
                st.error(f"**{a['title']}**\n\n{a['desc']}")
            elif a['type'] == 'WARNING':
                st.warning(f"**{a['title']}**\n\n{a['desc']}")
            elif a['type'] == 'GOOD':
                st.success(f"**{a['title']}**\n\n{a['desc']}")

    # Составы команд
    st.markdown("---")
    st.markdown("### 👥 Составы команд из лобби")
    team_c1, team_c2 = st.columns(2)
    
    def format_player_df(players):
        formatted = []
        for p in players:
            elo_str = f"{p['elo']} 🎯" if p.get('is_calibrating') else str(p['elo'])
            formatted.append({
                'Никнейм': p['nickname'],
                'Статус': p.get('tag', '🛡️ Обычный'),
                'ELO': elo_str,
                'K/D': p['kd'],
                'ADR': p['adr'],
                'HS%': p['hs'],
                'Матчи': p['matches'],
                'Винрейт%': p['winrate'],
                'Заметки': p.get('behavior_details', '')
            })
        return pd.DataFrame(formatted)
    
    with team_c1:
        st.markdown(f"#### 🔵 {t1['name']} (Средний ELO: {t1['avg_elo']} | K/D: {t1['avg_kd']:.2f})")
        df_p1 = format_player_df(t1['players'])
        st.dataframe(df_p1, use_container_width=True)
        
    with team_c2:
        st.markdown(f"#### 🔴 {t2['name']} (Средний ELO: {t2['avg_elo']} | K/D: {t2['avg_kd']:.2f})")
        df_p2 = format_player_df(t2['players'])
        st.dataframe(df_p2, use_container_width=True)

    # Раздел для ставок / лудиков
    st.markdown("---")
    st.header("🎰 Прогнозы для ставок (Value Betting Engine)")
    st.write("Введи коэффициенты из букмекерской конторы на этот матч для поиска **валуя (+EV)**:")
    
    b_c1, b_c2, b_c3 = st.columns(3)
    with b_c1:
        odds_1 = st.number_input(f"Коэффициент на {t1['name']}:", min_value=1.01, max_value=25.0, value=1.90, step=0.05)
    with b_c2:
        odds_2 = st.number_input(f"Коэффициент на {t2['name']}:", min_value=1.01, max_value=25.0, value=1.90, step=0.05)
    with b_c3:
        user_bank = st.number_input("Твой банк для ставок (руб./$):", min_value=100, max_value=1000000, value=10000, step=500)
        
    m_p1 = prob_t1
    m_p2 = 1.0 - prob_t1
    ev_1 = (m_p1 * odds_1 - 1.0) * 100
    ev_2 = (m_p2 * odds_2 - 1.0) * 100
    
    def kelly(p, odds):
        b = odds - 1.0
        q = 1.0 - p
        f = (b * p - q) / b
        return max(0.0, f * 0.25) # Fractional Kelly 25%

    res_b1, res_b2 = st.columns(2)
    with res_b1:
        if ev_1 > 0:
            k_pct = kelly(m_p1, odds_1) * 100
            sum_bet = round(user_bank * (k_pct / 100))
            st.success(f"🔥 **ВАЛУЙ НА {t1['name']}! (+{ev_1:.2f}% EV)**\n\nМодель оценивает победу в {m_p1*100:.1f}%, а бук даёт кэф {odds_1:.2f}. Рекомендуемая ставка по Келли: **{k_pct:.1f}% банка ({sum_bet} руб.)**")
        else:
            st.warning(f"❌ **Ставить на {t1['name']} невыгодно** (EV: {ev_1:+.2f}%)")
            
    with res_b2:
        if ev_2 > 0:
            k_pct = kelly(m_p2, odds_2) * 100
            sum_bet = round(user_bank * (k_pct / 100))
            st.success(f"🔥 **ВАЛУЙ НА {t2['name']}! (+{ev_2:.2f}% EV)**\n\nМодель оценивает победу в {m_p2*100:.1f}%, а бук даёт кэф {odds_2:.2f}. Рекомендуемая ставка по Келли: **{k_pct:.1f}% банка ({sum_bet} руб.)**")
        else:
            st.warning(f"❌ **Ставить на {t2['name']} невыгодно** (EV: {ev_2:+.2f}%)")
