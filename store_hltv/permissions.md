# Разрешения и ответы для Chrome Web Store (HLTV)

## Single purpose (одна цель)
EN: Show a pre-match and live win-probability panel, computed by a bundled machine-learning model, together with a map-veto breakdown and per-map win rates, on HLTV CS2 match pages.

RU: Показывать на страницах матчей HLTV панель с предматчевой и live-вероятностью победы, посчитанной встроенной ML-моделью, вместе с разбором вето и винрейтами команд по картам.

## permissions — нет
EN: The extension requests no Chrome permissions at all (`"permissions": []`). It does not use storage, tabs, cookies, clipboard or any other privileged API.

RU: Расширение не запрашивает ни одного разрешения Chrome (`"permissions": []`). Не использует storage, tabs, cookies, clipboard и другие привилегированные API.

## content script — *://www.hltv.org/matches/* и *://hltv.org/matches/*
EN: The content script runs only on HLTV match pages (`/matches/*`). It reads the match DOM that the user already has open (teams, veto, map scores, live scorebot) and inserts the analytics panel next to the site's own map statistics. It does not run on any other HLTV section or any other site.

RU: Content script работает только на страницах матчей HLTV (`/matches/*`). Он читает уже открытую пользователем разметку матча (команды, вето, счёт карт, live-scorebot) и вставляет панель рядом со статистикой карт самого сайта. На других разделах HLTV и на других сайтах не работает.

## web_accessible_resources — model_hltv.json, team_ratings.json
EN: The bundled CatBoost model (model_hltv.json) and the team-rating snapshot (team_ratings.json) must be readable by the content script so the prediction runs locally. Both are local data files shipped inside the extension; the extension loads no remote code and makes no network requests.

RU: Встроенная модель CatBoost (model_hltv.json) и снимок рейтингов команд (team_ratings.json) должны быть доступны content script, чтобы прогноз считался локально. Это локальные файлы данных внутри расширения; удалённый код не загружается, сетевых запросов расширение не делает.

## host_permissions — нет отдельных
EN: No separate host_permissions are declared. Access is limited to the content-script match patterns above (HLTV match pages only).

RU: Отдельные host_permissions не объявлены. Доступ ограничен match-паттернами content script выше (только страницы матчей HLTV).

## Data usage (вкладка Privacy practices)
- Does the extension collect user data? **No.**
- Does it transmit data to third parties? **No.**
- Does it use analytics, ads or tracking? **No.**
- Does it use remote code? **No.**
- Local storage: **none** (no storage permission, nothing persisted).
- Website content: the public match DOM already rendered in the user's browser is read locally to compute and render the panel; it is not collected or transmitted off-device.

## Пояснение для ревьюера (если попросят)
The extension is a read-only analytics overlay for HLTV CS2 match pages. It reads the match information the site has already rendered in the user's browser, computes a win probability with a bundled CatBoost model and a bundled rating snapshot, and renders a panel. There is no backend, no analytics, no data collection, no network requests and no Chrome permissions. The content script is limited to `hltv.org/matches/*`. It is a separate product from the developer's FACEIT extension because Chrome Web Store requires a single purpose per item and the two target different sites.