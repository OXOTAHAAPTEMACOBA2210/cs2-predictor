import json

nb = {
    'cells': [
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '# **Курсовая работа: Прогнозирование исходов матчей FACEIT (CS2) на основе машинного обучения**\n',
                '\n',
                '**Студент:** Кузьменко Владислав Александрович (РГАУ-МСХА им. К.А. Тимирязева, 09.03.02 «ИСиТ»)\n',
                '\n',
                '**Цель исследования:** Обучение и сравнительный анализ моделей бинарной классификации (Logistic Regression, Random Forest, CatBoost) для предсказания вероятности победы команд на соревновательной платформе FACEIT.'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## **1. Загрузка данных и первичный обзор**'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [
                'import pandas as pd\n',
                'import numpy as np\n',
                'import matplotlib.pyplot as plt\n',
                'import seaborn as sns\n',
                '\n',
                'df = pd.read_csv("../data/faceit_matches.csv")\n',
                'print("Размерность датасета:", df.shape)\n',
                'df.head(5)'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## **2. Разведочный анализ данных (EDA)**'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [
                'diff_cols = ["elo_diff", "kd_diff", "adr_diff", "map_winrate_diff", "streak_diff", "hs_diff", "team_1_win"]\n',
                'plt.figure(figsize=(9, 7))\n',
                'sns.heatmap(df[diff_cols].corr(), annot=True, fmt=".2f", cmap="coolwarm", square=True)\n',
                'plt.title("Корреляционная матрица дифференциальных признаков")\n',
                'plt.show()'
            ]
        },
        {
            'cell_type': 'markdown',
            'metadata': {},
            'source': [
                '## **3. Обучение и сравнительный анализ трех моделей ML**'
            ]
        },
        {
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [
                'from sklearn.model_selection import train_test_split\n',
                'from sklearn.preprocessing import StandardScaler\n',
                'from sklearn.linear_model import LogisticRegression\n',
                'from sklearn.ensemble import RandomForestClassifier\n',
                'from catboost import CatBoostClassifier\n',
                'from sklearn.metrics import accuracy_score, f1_score, roc_auc_score\n',
                '\n',
                'df_enc = pd.get_dummies(df, columns=["map_name"], drop_first=True)\n',
                'X = df_enc.drop(columns=["match_id", "team_1_win"])\n',
                'y = df_enc["team_1_win"]\n',
                '\n',
                'X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)\n',
                'scaler = StandardScaler()\n',
                'X_tr_sc = scaler.fit_transform(X_train)\n',
                'X_te_sc = scaler.transform(X_test)\n',
                '\n',
                'models = {\n',
                '    "Logistic Regression": (LogisticRegression(max_iter=1000), X_tr_sc, X_te_sc),\n',
                '    "Random Forest": (RandomForestClassifier(n_estimators=250, max_depth=12, random_state=42), X_train, X_test),\n',
                '    "CatBoost": (CatBoostClassifier(iterations=400, learning_rate=0.05, depth=6, verbose=0, random_seed=42), X_train, X_test)\n',
                '}\n',
                '\n',
                'for name, (clf, xtr, xte) in models.items():\n',
                '    clf.fit(xtr, y_train)\n',
                '    preds = clf.predict(xte)\n',
                '    probs = clf.predict_proba(xte)[:, 1]\n',
                '    print(f"[{name}] Acc: {accuracy_score(y_test, preds):.4f} | F1: {f1_score(y_test, preds):.4f} | AUC: {roc_auc_score(y_test, probs):.4f}")'
            ]
        }
    ],
    'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.13.0'}
    },
    'nbformat': 4,
    'nbformat_minor': 4
}

with open('faceit_ml_project/notebooks/faceit_coursework.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=2)
print("Notebook created successfully!")
