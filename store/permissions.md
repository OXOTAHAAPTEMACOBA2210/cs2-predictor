# Разрешения и ответы для Chrome Web Store

## Single purpose (одна цель)
EN: Show a pre-match analytics panel with win probability, player statistics and a map veto helper on FACEIT CS2 match room pages.

RU: Показывать панель с прогнозом победы, статистикой игроков и вето-помощником в комнатах матчей FACEIT CS2.

## host_permissions — https://www.faceit.com/*
EN: Required to read the public FACEIT match room and player statistics from www.faceit.com and to display the panel on that page. The extension only operates on faceit.com. Match data is processed locally in the browser and is not sent to the developer or any third-party server.

RU: Нужно, чтобы читать публичные данные комнаты матча и статистику игроков на www.faceit.com и показывать панель на странице. Расширение работает только на faceit.com, данные обрабатываются локально и не отправляются разработчику или третьим лицам.

## content script на https://www.faceit.com/*
EN: The content script injects the panel into the match room and tracks FACEIT's single-page-app navigation so the panel updates when the user opens another room. It runs only on faceit.com.

RU: Скрипт вставляет панель в комнату матча и отслеживает SPA-переходы FACEIT, чтобы панель обновлялась при открытии другой комнаты. Работает только на faceit.com.

## web_accessible_resources — model.json
EN: The bundled CatBoost model (model.json, ~1.8 MB) must be readable by the content script to run the prediction locally. It is a local data file shipped inside the extension; the extension does not load remote code.

RU: Встроенная модель CatBoost (model.json, ~1.8 МБ) должна быть доступна content script для локального прогноза. Это локальный файл внутри расширения; удалённый код не загружается.

## permissions — storage
EN: Used for one permission scope: `chrome.storage.local` as a 6-hour cache of the FACEIT match and statistics responses the extension already fetched, so that opening a second window of the same room does not re-request or re-compute stale data. Cached entries expire automatically and contain no credentials or user identifiers beyond public player IDs.

RU: Единственное использование — `chrome.storage.local` как кэш на 6 часов для ответов FACEIT об игре и статистике, которые расширение и так загрузило. Это нужно, чтобы два окна одной комнаты считали по одному снимку данных. Записи истекают сами, паролей и пользовательских идентификаторов не хранят.

## Data usage (вкладка Privacy practices)
- Does the extension collect user data? **No.**
- Does it transmit data to third parties? **No.**
- Does it use analytics, ads or tracking? **No.**
- Does it use remote code? **No.**
- Local storage: `chrome.storage.local`, TTL 6 hours, shared cache of public FACEIT match/statistics responses so all open windows of a room compute from the same snapshot. Cleared on retry and on expiry.
- Website content: public FACEIT match/player data is read and processed locally to render the panel; it is not collected or transmitted off-device.

## Пояснение для ревьюера (если попросят)
The extension is a read-only analytics overlay for FACEIT CS2 match rooms. It fetches the same public match and statistics endpoints that the FACEIT website uses in the user's browser, computes a prediction with a bundled model and renders a panel. There is no backend, no analytics and no data collection. The only host permission is faceit.com, and the content script is limited to that host.
