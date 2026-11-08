# Публикация в Chrome Web Store — пошагово

## 1. Что уже готово
- `dist/faceit-cs2-predictor-1.4.3.zip` — пакет расширения (manifest.json в корне).
- `store/screenshots/` — два скриншота 1280×800.
- `store/promo/` — плитка 440×280 (если собрана).
- `store/listing-ru.md` — название, краткое и подробное описание.
- `store/privacy-policy.html` — политика конфиденциальности (нужно захостить).
- `store/permissions.md` — обоснование разрешений и ответы по data usage.

## 2. Что нужно от тебя
1. Google-аккаунт.
2. Разовый взнос **$5** за аккаунт разработчика Chrome Web Store.
3. Верификация личности (имя, адрес, телефон) — может занять 1–2 дня.
4. Публичный URL политики конфиденциальности.
5. Email для поддержки (он будет виден в карточке).

## 3. Хостинг политики конфиденциальности
Самый простой бесплатный вариант — GitHub Pages:
1. Создай публичный репозиторий, например `faceit-cs2-predictor`.
2. Загрузи туда `store/privacy-policy.html` (можно переименовать в `index.html`).
3. В Settings → Pages включи GitHub Pages для ветки `main`.
4. Получишь URL вида `https://<username>.github.io/faceit-cs2-predictor/`.
5. Вставь этот URL в карточку магазина и в `store/listing-ru.md` вместо плейсхолдера.

Альтернативы: Notion (публичная страница), Google Sites, Qoder Sites. Главное — стабильный публичный URL без авторизации.

## 4. Аккаунт разработчика
1. Открой https://chrome.google.com/webstore/devconsole
2. Войди в Google-аккаунт.
3. Оплати регистрацию $5 (карта).
4. Заполни имя разработчика и контактные данные, пройди верификацию.
5. Дождись подтверждения аккаунта.

## 5. Загрузка расширения
1. В Dashboard нажми **New item**.
2. Загрузи `dist/faceit-cs2-predictor-1.4.3.zip`.
3. Проверь, что магазин не ругается на manifest и иконку.
4. Заполни карточку:
   - Name: `Faceit CS2 Predictor`
   - Summary: из `store/listing-ru.md`
   - Description: из `store/listing-ru.md`
   - Category: Fun или Sports
   - Language: Russian
   - Screenshots: два файла из `store/screenshots/` (1280×800)
   - Promo tile: из `store/promo/` (если есть)
   - Support email: свой email
   - Privacy policy URL: ссылка из шага 3
5. Вкладка **Privacy practices**:
   - Single purpose: из `store/permissions.md`
   - Permission justifications: из `store/permissions.md`
   - Data usage: «не собирает данные», без remote code, без аналитики.
6. Distribution:
   - Public
   - Все регионы (или только нужные)
   - Free
7. Нажми **Submit for review**.

## 6. Ревью
- Обычно 1–3 рабочих дня; у нового аккаунта может быть дольше.
- Следи за email: ревьюеры могут попросить уточнить разрешения или цель.
- Частые причины отказа:
  - слишком широкие разрешения (у нас только faceit.com);
  - несоответствие описания и функциональности;
  - вопросы по товарному знаку FACEIT;
  - отсутствие публичной политики конфиденциальности.
- Если откажут из-за имени/бренда — переименуй в запасное (например, `Lobby IQ`) и отправь снова.

## 7. Важно про имя
В магазине уже есть `Faceit Predictor` и `Recon — FACEIT CS2 Predictor`. Имя `Faceit CS2 Predictor` может потеряться в поиске и вызвать вопросы по бренду. Если хочешь, можно добавить отличительный суффикс: `Faceit CS2 Predictor — Veto & Stats` (37 символов) — это не меняет функциональность, только название.

## 8. После публикации
- Ссылка вида `https://chromewebstore.google.com/detail/<id>` — её можно кидать в Discord, Reddit, TikTok.
- Обновления: поднимаешь `version` в manifest, собираешь новый ZIP, загружаешь через **Package → Upload new package**.
- Не удаляй старую версию, пока новая не одобрена.

## 9. Переснять скриншоты после правок расширения
`store/preview.html` гоняет настоящий `chrome_extension/content.js` поверх демо-лобби,
поэтому после любой правки панели скриншоты надо переснять (иначе карточка показывает старый UI):

```
python -m http.server 8899 --bind 127.0.0.1     # из корня проекта, в отдельном окне
chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1280,800 \
  --virtual-time-budget=15000 --screenshot=store/screenshots/01-predict.png \
  "http://127.0.0.1:8899/store/preview.html?view=top"
chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1280,800 \
  --virtual-time-budget=15000 --screenshot=store/screenshots/02-veto.png \
  "http://127.0.0.1:8899/store/preview.html?view=veto"
```

Промо-плитка: `--window-size=440,280 --screenshot=store/promo/promo-440x280.png http://127.0.0.1:8899/store/promo/promo.html`.
Демо-лобби в preview синтетическое (team_Alpha/team_Beta) — это маркетинговый макет;
для проверки логики на реальных комнатах используй `tools/harness/`, а не preview.
