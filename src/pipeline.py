# -*- coding: utf-8 -*-
"""
Полный пайплайн машинного обучения для прогнозирования исходов матчей FACEIT (CS2)
1. Разведочный анализ данных (EDA) и сохранение графиков
2. Предобработка признаков и кодирование
3. Обучение 3 моделей:
   - Logistic Regression (бейзлайн)
   - Random Forest (ансамбль решающих деревьев)
   - CatBoost Classifier (градиентный бустинг)
4. Сравнение метрик: Accuracy, Precision, Recall, F1, ROC-AUC, LogLoss
5. Визуализация ROC-кривых, матрицы ошибок и важности признаков (Feature Importance)
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from catboost import CatBoostClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, log_loss, confusion_matrix, roc_curve
)

# Настройка эстетики графиков для курсовой работы (научный стиль)
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11
plt.rcParams['figure.autolayout'] = True

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

def run_eda(df):
    print(">>> [1/4] Выполнение разведочного анализа данных (EDA)...")
    
    # 1. Матрица корреляций ключевых дифференциальных признаков
    diff_cols = ['elo_diff', 'kd_diff', 'adr_diff', 'map_winrate_diff', 'streak_diff', 'hs_diff', 'elo_std_diff', 'team_1_win']
    corr = df[diff_cols].corr()
    
    plt.figure(figsize=(9, 7), dpi=300)
    mask = np.triu(np.ones_like(corr, dtype=bool))
    cmap = sns.diverging_palette(230, 20, as_cmap=True)
    sns.heatmap(corr, annot=True, fmt='.2f', cmap=cmap, mask=mask, cbar_kws={'label': 'Коэффициент корреляции Пирсона'}, square=True)
    plt.title("Корреляционная матрица дифференциальных признаков матча FACEIT", fontsize=13, pad=15)
    corr_path = os.path.join(FIG_DIR, "correlation_matrix.png")
    plt.savefig(corr_path)
    plt.close()
    print(f"    Сохранено: {corr_path}")
    
    # 2. Распределение разницы ELO и K/D в зависимости от исхода
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=300)
    
    sns.kdeplot(data=df, x='elo_diff', hue='team_1_win', common_norm=False, fill=True, palette={0: '#e74c3c', 1: '#2ecc71'}, alpha=0.4, ax=axes[0])
    axes[0].set_title("Распределение разницы ELO (Team 1 vs Team 2)")
    axes[0].set_xlabel("Разница ELO (elo_diff)")
    axes[0].set_ylabel("Плотность распределения")
    axes[0].legend(title="Победа Team 1", labels=['Победа', 'Поражение'])
    
    sns.kdeplot(data=df, x='kd_diff', hue='team_1_win', common_norm=False, fill=True, palette={0: '#e74c3c', 1: '#2ecc71'}, alpha=0.4, ax=axes[1])
    axes[1].set_title("Распределение разницы соотношения K/D")
    axes[1].set_xlabel("Разница среднего K/D (kd_diff)")
    axes[1].set_ylabel("Плотность распределения")
    axes[1].legend(title="Победа Team 1", labels=['Победа', 'Поражение'])
    
    dist_path = os.path.join(FIG_DIR, "elo_kd_distribution.png")
    plt.savefig(dist_path)
    plt.close()
    print(f"    Сохранено: {dist_path}")
    
    # 3. Распределение матчей по картам соревновательного пула CS2
    plt.figure(figsize=(10, 4.5), dpi=300)
    order = df['map_name'].value_counts().index
    palette = sns.color_palette("mako", len(order))
    ax = sns.countplot(data=df, x='map_name', order=order, palette=palette)
    plt.title("Распределение матчей по картам пула FACEIT CS2", fontsize=13, pad=12)
    plt.xlabel("Карта (Map)")
    plt.ylabel("Количество сыгранных матчей")
    for p in ax.patches:
        ax.annotate(f"{int(p.get_height()):,}", (p.get_x() + p.get_width() / 2., p.get_height() / 2),
                    ha='center', va='center', color='white', fontweight='bold', fontsize=10)
    map_path = os.path.join(FIG_DIR, "map_distribution.png")
    plt.savefig(map_path)
    plt.close()
    print(f"    Сохранено: {map_path}")

def run_ml_pipeline():
    csv_file = os.path.join(DATA_DIR, "faceit_matches.csv")
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"Файл {csv_file} не найден. Сначала запустите dataset_generator.py")
        
    df = pd.read_csv(csv_file)
    run_eda(df)
    
    print("\n>>> [2/4] Подготовка признаков и разбиение выборки...")
    
    # Кодирование категориальной переменной map_name (One-Hot Encoding)
    df_encoded = pd.get_dummies(df, columns=['map_name'], drop_first=True)
    
    # Выделение матрицы признаков X и целевого вектора y
    drop_cols = ['match_id', 'team_1_win']
    feature_cols = [c for c in df_encoded.columns if c not in drop_cols]
    
    X = df_encoded[feature_cols]
    y = df_encoded['team_1_win']
    
    # Стратифицированное разбиение: 80% обучение, 20% валидация/тест
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    
    # Масштабирование признаков для линейных моделей
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    print(f"    Обучающая выборка: {X_train.shape[0]} матчей")
    print(f"    Тестовая выборка:   {X_test.shape[0]} матчей")
    print(f"    Количество признаков: {X.shape[1]}")
    
    print("\n>>> [3/4] Обучение и сравнительное тестирование моделей...")
    
    models = {
        "Логистическая регрессия": LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        "Случайный лес (Random Forest)": RandomForestClassifier(n_estimators=250, max_depth=12, min_samples_leaf=4, n_jobs=-1, random_state=42),
        "CatBoost Classifier": CatBoostClassifier(iterations=450, learning_rate=0.05, depth=6, eval_metric='AUC', verbose=0, random_seed=42)
    }
    
    results = {}
    y_preds = {}
    y_probs = {}
    
    for name, model in models.items():
        print(f"    Обучение: {name}...")
        if name == "Логистическая регрессия":
            model.fit(X_train_scaled, y_train)
            pred = model.predict(X_test_scaled)
            prob = model.predict_proba(X_test_scaled)[:, 1]
        else:
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            prob = model.predict_proba(X_test)[:, 1]
            
        acc = accuracy_score(y_test, pred)
        prec = precision_score(y_test, pred)
        rec = recall_score(y_test, pred)
        f1 = f1_score(y_test, pred)
        auc = roc_auc_score(y_test, prob)
        loss = log_loss(y_test, prob)
        
        results[name] = {
            "Accuracy": round(acc, 4),
            "Precision": round(prec, 4),
            "Recall": round(rec, 4),
            "F1-Score": round(f1, 4),
            "ROC-AUC": round(auc, 4),
            "Log-Loss": round(loss, 4)
        }
        y_preds[name] = pred
        y_probs[name] = prob
        
    # Сохранение результатов в файл метрик
    results_df = pd.DataFrame(results).T
    summary_csv = os.path.join(DATA_DIR, "metrics_summary.csv")
    results_df.to_csv(summary_csv)
    
    summary_json = os.path.join(DATA_DIR, "metrics_summary.json")
    with open(summary_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\nСводная таблица метрик:\n{results_df}")
    
    print("\n>>> [4/4] Построение аналитических визуализаций и кривых...")
    
    # 1. Сравнение ROC-кривых всех трех моделей
    plt.figure(figsize=(8, 6), dpi=300)
    palette_colors = {'Логистическая регрессия': '#3498db', 'Случайный лес (Random Forest)': '#e67e22', 'CatBoost Classifier': '#2ecc71'}
    
    for name in models.keys():
        fpr, tpr, _ = roc_curve(y_test, y_probs[name])
        auc_val = results[name]['ROC-AUC']
        plt.plot(fpr, tpr, label=f"{name} (AUC = {auc_val:.3f})", color=palette_colors[name], lw=2.2)
        
    plt.plot([0, 1], [0, 1], 'k--', lw=1.2, label='Случайный классификатор (AUC = 0.500)')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate (1 - Специфичность)')
    plt.ylabel('True Positive Rate (Чувствительность / Recall)')
    plt.title('Сравнение ROC-кривых моделей прогнозирования победы FACEIT', fontsize=12, pad=12)
    plt.legend(loc="lower right", frameon=True)
    roc_path = os.path.join(FIG_DIR, "roc_curves.png")
    plt.savefig(roc_path)
    plt.close()
    print(f"    Сохранено: {roc_path}")
    
    # 2. Матрицы ошибок (Confusion Matrix)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), dpi=300)
    for idx, (name, pred) in enumerate(y_preds.items()):
        cm = confusion_matrix(y_test, pred)
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[idx], cbar=False,
                    xticklabels=['Team 2 Win', 'Team 1 Win'], yticklabels=['Team 2 Win', 'Team 1 Win'])
        axes[idx].set_title(f"{name}\nAcc: {results[name]['Accuracy']:.3f} | F1: {results[name]['F1-Score']:.3f}")
        axes[idx].set_xlabel("Предсказанный класс")
        axes[idx].set_ylabel("Истинный класс")
    cm_path = os.path.join(FIG_DIR, "confusion_matrices.png")
    plt.savefig(cm_path)
    plt.close()
    print(f"    Сохранено: {cm_path}")
    
    # 3. Важность признаков (Feature Importance) от CatBoost
    cb_model = models["CatBoost Classifier"]
    importances = cb_model.get_feature_importance()
    feat_imp = pd.Series(importances, index=feature_cols).sort_values(ascending=True)
    top_feats = feat_imp.tail(12)
    
    plt.figure(figsize=(10, 6), dpi=300)
    top_feats.plot(kind='barh', color='#34495e', edgecolor='none')
    plt.title("Топ-12 наиболее информативных признаков (CatBoost Feature Importance)", fontsize=12, pad=12)
    plt.xlabel("Относительная важность признака (%)")
    plt.ylabel("Признак")
    for i, v in enumerate(top_feats):
        plt.text(v + 0.3, i, f"{v:.1f}%", va='center', fontweight='bold', color='#2c3e50', fontsize=9.5)
    plt.xlim(0, max(top_feats) * 1.15)
    fi_path = os.path.join(FIG_DIR, "feature_importance.png")
    plt.savefig(fi_path)
    plt.close()
    print(f"    Сохранено: {fi_path}")

    print("\n[УСПЕХ] Пайплайн успешно завершен! Все метрики и графики готовы для LaTeX.")
    return results

if __name__ == "__main__":
    run_ml_pipeline()
