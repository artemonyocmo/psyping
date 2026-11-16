let state = {
  settings: {},
  channels: [],
  prompts: [],
  logs: [],
  activeTab: 'overview',
  nextPingTime: null,
  liveLogId: null
};

// Web Audio API Gentle Mindfulness Chime Synthesizer
function playMindfulnessChime() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    
    // Harmonic frequencies for Tibetan Bowl (F#4 root)
    const freqs = [369.99, 740.0, 1110.0, 1480.0];
    const now = ctx.currentTime;
    
    freqs.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      
      osc.type = idx === 0 ? 'sine' : 'triangle';
      osc.frequency.setValueAtTime(freq, now);
      
      // Gentle decay envelope
      const maxGain = idx === 0 ? 0.3 : 0.08 / idx;
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(maxGain, now + 0.05);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 3.5);
      
      osc.connect(gain);
      gain.connect(ctx.destination);
      
      osc.start(now);
      osc.stop(now + 3.6);
    });
  } catch (e) {
    console.error("Audio chime error:", e);
  }
}

// Browser Notifications API
function checkNotificationSupport() {
  const btn = document.getElementById('btn-browser-notif');
  const label = document.getElementById('notif-label');
  const icon = document.getElementById('notif-icon');
  
  if (!("Notification" in window)) {
    if (btn) btn.style.display = 'none';
    return;
  }
  
  if (Notification.permission === 'granted') {
    if (icon) icon.innerText = '✓';
    if (label) label.innerText = 'Пуши активны';
    if (btn) btn.classList.add('border-emerald-500/40', 'text-emerald-400');
  } else if (Notification.permission === 'denied') {
    if (icon) icon.innerText = '✕';
    if (label) label.innerText = 'Пуши заблокированы';
  }
}

async function enableBrowserNotifications() {
  if (!("Notification" in window)) return;
  const permission = await Notification.requestPermission();
  checkNotificationSupport();
  if (permission === 'granted') {
    new Notification('PsyPing активирован', {
      body: 'Теперь случайные напоминания будут приходить прямо на этот экран.',
      icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">Ψ</text></svg>'
    });
  }
}

function showBrowserNotification(title, text, logId) {
  if ("Notification" in window && Notification.permission === 'granted') {
    const notif = new Notification(title, {
      body: text,
      icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">Ψ</text></svg>',
      requireInteraction: true
    });
    notif.onclick = () => {
      window.focus();
      if (logId) acknowledgePing(logId);
      notif.close();
    };
  }
}

function copyShareLink() {
  const url = window.location.origin + '/?u=' + (state.userId || 'default');
  navigator.clipboard.writeText(url).then(() => {
    const label = document.getElementById('share-label');
    if (label) {
      label.innerText = 'Скопировано! ✓';
      setTimeout(() => label.innerText = 'Мой линк', 2000);
    }
  });
}

// Navigation Tabs
function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('border-emerald-500', 'text-emerald-400');
    btn.classList.add('border-transparent', 'text-slate-400');
  });
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));

  const activeBtn = document.getElementById(`tab-btn-${tabId}`);
  const activeContent = document.getElementById(`tab-content-${tabId}`) || document.getElementById(`tab-${tabId}`);
  if (activeBtn) {
    activeBtn.classList.remove('border-transparent', 'text-slate-400');
    activeBtn.classList.add('border-emerald-500', 'text-emerald-400');
  }
  if (activeContent) {
    activeContent.classList.remove('hidden');
  }
  
  if (tabId === 'channels') renderChannels();
  if (tabId === 'prompts') renderPrompts();
}

// API Calls & Render
async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.settings = data.settings || {};
    state.userId = data.user_id || 'default';
    state.logs = data.recent_logs || [];
    
    // Status badge
    const badge = document.getElementById('status-badge');
    if (state.settings.is_paused) {
      badge.innerText = 'На паузе';
      badge.className = 'px-2 py-0.5 text-xs font-medium rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20';
    } else {
      badge.innerText = 'Активен';
      badge.className = 'px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    }

    // Next Ping
    if (state.settings.next_run_at) {
      state.nextPingTime = new Date(state.settings.next_run_at);
      document.getElementById('stat-next-ping').innerText = state.nextPingTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
      document.getElementById('stat-next-ping').innerText = '--:--';
    }

    // Ack rate
    document.getElementById('stat-ack-rate').innerText = `${data.ack_rate_percent}%`;
    document.getElementById('stat-ack-counts').innerText = `${data.acked_pings} из ${data.total_pings} зафиксировано`;

    // Counts
    document.getElementById('stat-active-channels').innerText = `${data.active_channels_count} / ${data.total_channels_count}`;
    document.getElementById('stat-prompts-count').innerText = `${data.active_prompts_count} тем`;

    // Populate Settings form inputs
    populateSettingsInputs();
    
    // Fetch channels and prompts
    await loadChannels();
    await loadPrompts();
    renderLogs();
    renderRouletteBars();
  } catch (e) {
    console.error("Failed to load status:", e);
  }
}

async function loadChannels() {
  const res = await fetch('/api/channels');
  const data = await res.json();
  state.channels = data.channels || [];
  renderChannels();
  renderRouletteBars();
}

async function loadPrompts() {
  const res = await fetch('/api/prompts');
  const data = await res.json();
  state.prompts = data.prompts || [];
  renderPrompts();
}

function renderRouletteBars() {
  const container = document.getElementById('roulette-bars');
  if (!container) return;
  container.innerHTML = '';

  const enabled = state.channels.filter(c => c.enabled);
  const totalWeight = enabled.reduce((acc, c) => acc + (c.effective_weight || c.weight || 1.0), 0);

  enabled.forEach(c => {
    const effW = c.effective_weight || c.weight || 1.0;
    const pct = totalWeight > 0 ? Math.round((effW / totalWeight) * 100) : 0;
    
    const row = document.createElement('div');
    row.className = 'space-y-1';
    row.innerHTML = `
      <div class="flex items-center justify-between text-xs">
        <span class="font-medium text-slate-300">${c.name}</span>
        <span class="text-slate-400 font-mono">${pct}% (вес ${effW})</span>
      </div>
      <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
        <div class="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all duration-500" style="width: ${pct}%"></div>
      </div>
    `;
    container.appendChild(row);
  });
}

function renderLogs() {
  const list = document.getElementById('logs-list');
  if (!list) return;
  list.innerHTML = '';

  if (state.logs.length === 0) {
    list.innerHTML = '<div class="py-6 text-center text-xs text-slate-500">Пока не было отправлено ни одного импульса</div>';
    return;
  }

  state.logs.slice(0, 10).forEach(log => {
    const isAck = !!log.acknowledged_at;
    const dateStr = new Date(log.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    const item = document.createElement('div');
    item.className = 'py-3 flex items-center justify-between gap-4';
    item.innerHTML = `
      <div class="flex items-start gap-3 min-w-0">
        <div class="w-2 h-2 rounded-full mt-2 ${isAck ? 'bg-emerald-400' : 'bg-amber-400/80'} shrink-0"></div>
        <div class="min-w-0">
          <div class="text-xs text-slate-400 flex items-center gap-2">
            <span>${dateStr}</span>
            <span>•</span>
            <span class="font-medium text-slate-300">${log.channel_name || log.channel_id}</span>
          </div>
          <div class="text-sm font-medium text-slate-200 truncate mt-0.5">${log.generated_text}</div>
          ${log.error_message ? `<div class="text-xs text-red-400 mt-0.5">Ошибка: ${log.error_message}</div>` : ''}
        </div>
      </div>
      <div class="shrink-0">
        ${isAck 
          ? `<span class="px-2.5 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-lg border border-emerald-500/20">Сделано ✓</span>`
          : `<button onclick="acknowledgePing('${log.id}')" class="px-3 py-1 bg-slate-800 hover:bg-emerald-600 text-slate-200 hover:text-white text-xs font-semibold rounded-lg border border-slate-700 transition">Сделал ✓</button>`
        }
      </div>
    `;
    list.appendChild(item);
  });
}

function renderChannels() {
  const grid = document.getElementById('channels-grid');
  if (!grid) return;
  grid.innerHTML = '';

  state.channels.forEach(c => {
    const card = document.createElement('div');
    card.className = `bg-slate-900 border ${c.enabled ? 'border-slate-800' : 'border-slate-800/40 opacity-60'} rounded-2xl p-5 flex flex-col justify-between`;
    card.innerHTML = `
      <div>
        <div class="flex items-start justify-between gap-2 mb-2">
          <h3 class="font-bold text-base text-white">${c.name}</h3>
          <input type="checkbox" ${c.enabled ? 'checked' : ''} onchange="toggleChannel('${c.id}', this.checked)" class="w-5 h-5 accent-emerald-500 rounded cursor-pointer">
        </div>
        <p class="text-xs text-slate-400 mb-4">${c.description}</p>
        
        <div class="space-y-3 mb-4">
          <div>
            <div class="flex justify-between text-xs text-slate-400 mb-1">
              <span>Базовый вес рулетки:</span>
              <span id="weight-val-${c.id}" class="font-mono text-emerald-400 font-bold">${c.weight}</span>
            </div>
            <input type="range" min="0.2" max="2.5" step="0.1" value="${c.weight}" onchange="updateChannelWeight('${c.id}', this.value)" oninput="document.getElementById('weight-val-${c.id}').innerText = this.value" class="w-full accent-emerald-500">
          </div>
          
          <div class="grid grid-cols-2 gap-2 text-xs bg-slate-950 p-2.5 rounded-xl border border-slate-800/80">
            <div>
              <div class="text-slate-500">Отправлено</div>
              <div class="font-semibold text-slate-300">${c.total_sent}</div>
            </div>
            <div>
              <div class="text-slate-500">Подтверждено</div>
              <div class="font-semibold text-emerald-400">${c.total_acknowledged}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="pt-2 border-t border-slate-800/80 flex justify-end">
        <button onclick="testChannel('${c.id}')" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition">
          Тест этого канала ⚡
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function renderPrompts() {
  const grid = document.getElementById('prompts-grid');
  if (!grid) return;
  grid.innerHTML = '';

  const catFilter = document.getElementById('prompt-cat-filter')?.value || '';
  const filtered = state.prompts.filter(p => !catFilter || p.category === catFilter);

  const categoryNames = {
    body: '🧘‍♂️ Тело & Соматика',
    modes_schemas: '🧠 Режимы/Схемы',
    emotion: '🌊 Эмоции',
    grounding: '⚓ Заземление',
    values: '🧭 Ценности',
    micro_break: '☕ Передышка'
  };

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = 'bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between';
    card.innerHTML = `
      <div>
        <div class="flex items-center justify-between gap-2 mb-2">
          <span class="px-2 py-0.5 bg-slate-800 text-emerald-400 text-xs font-semibold rounded-md border border-slate-700">
            ${categoryNames[p.category] || p.category}
          </span>
          <span class="text-xs text-slate-500">Использовано: ${p.use_count}</span>
        </div>
        <p class="text-sm font-medium text-slate-200 mb-3">${p.base_text}</p>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
        <button onclick="testWithPrompt('${p.id}')" class="text-emerald-400 hover:text-emerald-300 font-medium">
          Запустить этот ⚡
        </button>
        <button onclick="deletePrompt('${p.id}')" class="text-red-400/80 hover:text-red-400">
          Удалить
        </button>
      </div>
    `;
    grid.appendChild(card);
  });
}

function filterPrompts() {
  renderPrompts();
}

function populateSettingsInputs() {
  const s = state.settings;
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null) el.value = val;
  };
  
  setVal('setting-quiet-start', s.quiet_hours_start || '22:00');
  setVal('setting-quiet-end', s.quiet_hours_end || '09:00');
  setVal('setting-target-count', s.daily_target_count || 4);
  const countVal = document.getElementById('target-count-val');
  if (countVal) countVal.innerText = s.daily_target_count || 4;
  
  const pausedBox = document.getElementById('setting-is-paused');
  if (pausedBox) pausedBox.checked = !!s.is_paused;

  setVal('setting-llm-provider', s.llm_provider || 'fallback');
  setVal('setting-gemini-key', s.gemini_api_key || '');
  setVal('setting-openai-key', s.openai_api_key || '');
  setVal('setting-tts-voice', s.tts_voice || 'ru-RU-DmitryNeural');
  setVal('setting-tg-token', s.telegram_bot_token || '');
  setVal('setting-tg-chat', s.telegram_chat_id || '');
  setVal('setting-ntfy-topic', s.ntfy_topic || 'psyping_alerts');
  setVal('setting-webhook-url', s.webhook_url || '');
}

async function saveAllSettings() {
  const payload = {
    quiet_hours_start: document.getElementById('setting-quiet-start').value,
    quiet_hours_end: document.getElementById('setting-quiet-end').value,
    daily_target_count: parseInt(document.getElementById('setting-target-count').value),
    is_paused: document.getElementById('setting-is-paused').checked ? 1 : 0,
    llm_provider: document.getElementById('setting-llm-provider').value,
    gemini_api_key: document.getElementById('setting-gemini-key').value,
    openai_api_key: document.getElementById('setting-openai-key').value,
    tts_voice: document.getElementById('setting-tts-voice').value,
    telegram_bot_token: document.getElementById('setting-tg-token').value,
    telegram_chat_id: document.getElementById('setting-tg-chat').value,
    ntfy_topic: document.getElementById('setting-ntfy-topic').value,
    webhook_url: document.getElementById('setting-webhook-url').value
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert('Настройки успешно сохранены!');
      loadStatus();
    }
  } catch (e) {
    alert('Ошибка сохранения настроек: ' + e);
  }
}

async function toggleChannel(channelId, enabled) {
  await fetch(`/api/channels/${channelId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: enabled ? 1 : 0 })
  });
  loadChannels();
}

async function updateChannelWeight(channelId, weight) {
  await fetch(`/api/channels/${channelId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weight: parseFloat(weight) })
  });
  loadChannels();
}

async function triggerQuickPing() {
  try {
    const res = await fetch('/api/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      playMindfulnessChime();
      loadStatus();
    } else {
      alert('Ошибка отправки: ' + (data.error || 'неизвестная ошибка'));
    }
  } catch (e) {
    alert('Сетевая ошибка: ' + e);
  }
}

async function testChannel(channelId) {
  try {
    const res = await fetch('/api/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel_id: channelId })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Успешно отправлено через ${channelId}!`);
      loadStatus();
    } else {
      alert(`Ошибка канала ${channelId}: ${data.error}`);
    }
  } catch (e) {
    alert('Ошибка: ' + e);
  }
}

async function testWithPrompt(promptId) {
  try {
    const res = await fetch('/api/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt_id: promptId })
    });
    const data = await res.json();
    if (data.success) {
      loadStatus();
      switchTab('overview');
    } else {
      alert('Ошибка: ' + data.error);
    }
  } catch (e) {
    alert('Ошибка: ' + e);
  }
}

async function acknowledgePing(logId) {
  try {
    const res = await fetch(`/api/acknowledge/${logId}`, { method: 'POST' });
    if (res.ok) {
      // Hide live notification banner if matching
      if (state.liveLogId === logId) {
        document.getElementById('live-notification').classList.add('hidden');
      }
      loadStatus();
    }
  } catch (e) {
    console.error(e);
  }
}

function acknowledgeLive() {
  if (state.liveLogId) {
    acknowledgePing(state.liveLogId);
  }
}

async function testMutationPreview() {
  const text = document.getElementById('mutation-test-input').value;
  const resultDiv = document.getElementById('mutation-preview-result');
  try {
    const res = await fetch('/api/preview-mutation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, category: 'body' })
    });
    const data = await res.json();
    resultDiv.classList.remove('hidden');
    resultDiv.innerHTML = `<strong>Результат:</strong> ${data.mutated}`;
  } catch (e) {
    console.error(e);
  }
}

async function deletePrompt(promptId) {
  if (!confirm('Удалить эту тему?')) return;
  await fetch(`/api/prompts/${promptId}`, { method: 'DELETE' });
  loadPrompts();
}

function openNewPromptModal() {
  const text = prompt('Введите базовый текст напоминания:');
  if (!text) return;
  const cat = prompt('Категория (body, modes_schemas, emotion, grounding, values, micro_break):', 'body');
  if (!cat) return;

  fetch('/api/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category: cat, base_text: text })
  }).then(() => loadPrompts());
}

// Live Countdown loop
setInterval(() => {
  if (!state.nextPingTime) return;
  const now = new Date();
  const diffMs = state.nextPingTime - now;
  const el = document.getElementById('stat-next-countdown');
  if (!el) return;

  if (diffMs <= 0) {
    el.innerText = 'Импульс запланирован прямо сейчас';
    el.className = 'text-xs text-amber-400 font-medium mt-1';
  } else {
    const mins = Math.floor(diffMs / 60000);
    const secs = Math.floor((diffMs % 60000) / 1000);
    el.innerText = `Примерно через ${mins} мин ${secs} сек`;
    el.className = 'text-xs text-emerald-400 font-medium mt-1';
  }
}, 1000);

// Server-Sent Events (SSE) Listener for real-time live events
function setupSSE() {
  const eventSource = new EventSource('/api/events');
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'ping') {
        // 1. Play harmonic audio chime
        playMindfulnessChime();

        // 2. Show desktop / browser notification
        showBrowserNotification(data.title || 'PsyPing', data.text, data.log_id);

        // 3. Show in-app banner
        state.liveLogId = data.log_id;
        document.getElementById('live-category').innerText = data.category || 'Импульс осознанности';
        document.getElementById('live-text').innerText = data.text;
        document.getElementById('live-notification').classList.remove('hidden');

        // 4. Reload logs
        loadStatus();
      }
    } catch (e) {
      console.error("SSE parse error:", e);
    }
  };
  eventSource.onerror = () => {
    // Reconnects automatically
  };
}

// Initial boot
window.addEventListener('DOMContentLoaded', () => {
  checkNotificationSupport();
  loadStatus();
  setupSSE();
});
