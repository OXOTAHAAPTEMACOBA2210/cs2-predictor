# Публикация в Chrome Web Store — пошагово (HLTV)

Это **второй, отдельный** товар магазина, не обновление Faceit CS2 Predictor:
у Chrome Web Store политика «single purpose», а домены и назначение разные.
Загружается как New item в том же аккаунте разработчика.

## 1. Что уже готово
- `dist/cs2-pro-predictor-hltv-0.2.0.zip` — пакет расширения (manifest.json в корне, 7 файлов).
- `store_hltv/screenshots/01-predict.png`, `02-live.png` — два скриншота 1280×800.
- `store_hltv/promo/promo-440x280.png` — плитка 440×280.
- `store_hltv/listing-ru.md` — название, краткое и подробное описание.
- `store_hltv/privacy-policy.html` — политика конфиденциальности (нужно захостить).
- `store_hltv/permissions.md` — обоснование разрешений и ответы по data usage.

Скриншоты сняты с **реальных** страниц матчей (Spirit–FUT, будущий; OG–9INE, live),
а не с выдуманных данных: разметка получена живым браузером, панель — настоящий
content.js расширения. Цифры на кадрах совпадают с прогоном офлайн-стендов.

## 2. Что нужно от тебя
1. Google-аккаунт (тот же, что для FACEIT-расширения, если уже есть).
2. Разовый взнос **$5** за аккаунт разработчика (если ещё не оплачен).
3. Верификация личности (имя, адрес, телефон) — 1–2 дня.
4. Публичный URL политики конфиденциальности (можно отдельная страница в том же репозитории).
5. Email для поддержки (виден в карточке).

## 3. Хостинг политики конфиденциальности
GitHub Pages (бесплатно):
1. Публичный репозиторий, например `cs2-pro-predictor`.
2. Положи `store_hltv/privacy-policy.html` как `hltv-privacy.html` (или в подпапку).
3. Settings → Pages → ветка `main`.
4. URL вида `https://<username>.github.io/cs2-pro-predictor/hltv-privacy.html`.
5. Вставь URL в карточку и в `store_hltv/listing-ru.md` вместо плейсхолдера.

Альтернативы: Notion, Google Sites, Qoder Sites. Главное — стабильный публичный URL без авторизации.

## 4. Загрузка расширения
1. https://chrome.google.com/webstore/devconsole → **New item**.
2. Загрузи `dist/cs2-pro-predictor-hltv-0.2.0.zip`.
3. Карточка:
   - Name: `CS2 Pro Predictor (HLTV)`
   - Summary / Description: из `store_hltv/listing-ru.md`
   - Category: Fun или Sports
   - Language: Russian
   - Screenshots: два файла из `store_hltv/screenshots/` (1280×800)
   - Promo tile: `store_hltv/promo/promo-440x280.png`
   - Support email: свой email
   - Privacy policy URL: ссылка из шага 3
4. Вкладка **Privacy practices**:
   - Single purpose: из `store_hltv/permissions.md`
   - Permission justifications: из `store_hltv/permissions.md` (разрешений нет; обосновать content script и web_accessible_resources)
   - Data usage: «не собирает данные», без remote code, без аналитики, без локального хранилища.
5. Distribution: Public, все регионы, Free.
6. **Submit for review**.

## 5. Ревью
- Обычно 1–3 рабочих дня; у нового аккаунта дольше.
- Частые причины отказа и как закрыты:
  - широкие разрешения → у нас `permissions: []`, content script только `hltv.org/matches/*`;
  - несоответствие описания и функциональности → описание повторяет панель один в один;
  - товарный знак HLTV → в названии и описании есть «Не связано с HLTV»; при претензии переименуй (например `Pro CS2 Predictor for HLTV`);
  - отсутствие публичной политики → шаг 3.
- Если спросят «почему два расширения» — ответ в `permissions.md`: single purpose и разные сайты.

## 6. После публикации и обновления
- Ссылка `https://chromewebstore.google.com/detail/<id>` — кидать в Discord/Reddit.
- Обновление модели: прогнать `src/hltv_train.py` (пересоберёт `model_hltv.json` и
  `team_ratings.json`), поднять `version` в manifest, пересобрать ZIP, загрузить через
  **Package → Upload new package**. Старую версию не удалять, пока новая не одобрена.
- Снимок рейтингов статичен (as_of в `team_ratings.json`); без переобучения панель
  честно откажется прогнозировать матчи, начавшиеся до этой даты.

## 7. Переснять скриншоты после правок расширения
Превью инлайнит бандл, но content.js и styles.css берёт по абсолютным путям,
поэтому после любой правки расширения превью надо пересобрать и переснять:

```
python tools/harness/hltv_preview.py tools/harness/hltv/fragments/upcoming-spirit-fut.json predict store_hltv/preview-predict.html
python tools/harness/hltv_preview.py tools/harness/hltv/fragments/live-og-9ine.json     live    store_hltv/preview-live.html
python -m http.server 8899 --bind 127.0.0.1     # из корня проекта, в отдельном окне
chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1280,800 \
  --virtual-time-budget=8000 --screenshot=store_hltv/screenshots/01-predict.png \
  http://127.0.0.1:8899/store_hltv/preview-predict.html
chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1280,800 \
  --virtual-time-budget=8000 --screenshot=store_hltv/screenshots/02-live.png \
  http://127.0.0.1:8899/store_hltv/preview-live.html
chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=440,280 \
  --virtual-time-budget=4000 --screenshot=store_hltv/promo/promo-440x280.png \
  http://127.0.0.1:8899/store_hltv/promo/promo.html
```

Фрагменты реальных страниц обновляются через `tools/harness/frag_server.py` (:8766)
и browser-use; сохранённая страница HLTV как источник не годится (DOM гидратируется их JS).