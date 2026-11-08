// Faceit CS2 Predictor — статус в popup (реальная проверка, а не только URL)
(async () => {
  const node = document.getElementById('status');
  const set = (cls, text) => {
    node.className = 'status ' + cls;
    node.textContent = text;
  };

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = (tab && tab.url) || '';

    if (!/^https:\/\/www\.faceit\.com\//.test(url)) {
      set('wait', 'Это не FACEIT. Открой сайт и комнату матча.');
      return;
    }

    const room = url.match(/\/room\/(\d-[0-9a-zA-Z-]+)/);
    const resp = await new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { type: 'fai-ping' }, (r) => {
        resolve(chrome.runtime.lastError ? null : r);
      });
    });

    if (!resp) {
      set('wait', 'Скрипт на этой вкладке не запущен. Нажми F5 на странице FACEIT.');
    } else if (!room) {
      set('wait', 'Скрипт активен. Открой комнату матча — панель появится сама.');
    } else if (resp.hasHud) {
      set('ok', 'Панель работает в комнате ' + room[1].slice(0, 10) + '…');
    } else {
      set('wait', 'Скрипт активен, панель закрыта. Обнови страницу (F5).');
    }
  } catch (e) {
    set('wait', 'Не удалось проверить вкладку.');
  }
})();
