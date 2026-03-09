const botUrlEl = document.getElementById('bot-url');
const statusEl = document.getElementById('status');

// Load saved values
chrome.storage.local.get(['botUrl', 'lastSync', 'lastStatus'], data => {
    botUrlEl.value = data.botUrl || 'http://127.0.0.1:5000';
    const ts = data.lastSync ? new Date(data.lastSync).toLocaleTimeString() : 'never';
    const st = data.lastStatus || 'unknown';
    const cls = st === 'ok' ? 'ok' : 'err';
    statusEl.innerHTML = `Last sync: <span class="${cls}">${ts} (${st})</span>`;
});

document.getElementById('save-btn').addEventListener('click', () => {
    let url = botUrlEl.value.trim().replace(/\/$/, '');
    if (url && !url.startsWith('http')) {
        url = 'http://' + url;
    }
    chrome.runtime.sendMessage({ action: 'set_bot_url', url }, resp => {
        statusEl.innerHTML = resp && resp.ok
            ? '<span class="ok">URL saved ✓</span>'
            : '<span class="err">Error saving URL</span>';
    });
});

document.getElementById('sync-btn').addEventListener('click', () => {
    statusEl.innerHTML = '⏳ Syncing…';
    chrome.runtime.sendMessage({ action: 'sync_now' }, resp => {
        statusEl.innerHTML = resp && resp.ok
            ? '<span class="ok">Sync triggered ✓</span>'
            : '<span class="err">Could not trigger sync</span>';
    });
});

document.getElementById('open-panel-btn').addEventListener('click', () => {
    const url = botUrlEl.value.trim().replace(/\/$/, '') || 'http://127.0.0.1:5000';
    window.open(url, '_blank');
});
