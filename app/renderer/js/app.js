// 앱 셸 : 엔진 상태 · 라우팅 · 상단 상태 바
import { api, setBase } from './api.js';
import { h, clear, stateView } from './ui.js';
import * as scenarios from './views/scenarios.js';
import * as run from './views/run.js';
import * as report from './views/report.js';
import * as history from './views/history.js';

const VIEWS = { scenarios, run, reports: report, history };
const HEALTH_MS = 5000;

const $view = document.getElementById('view');
const $topbar = document.getElementById('topbar');
const $overlay = document.getElementById('overlay');
const $foot = document.getElementById('engine-foot');
const $navLive = document.getElementById('nav-live');

const bridge = window.retrace || null;  // preload 없으면 기본 URL로 동작

// 공유 상태
const ctx = {
  health: null,
  lastRunId: null,
  navigate(hash) {
    if (location.hash === hash) render();
    else location.hash = hash;
  },
  async refreshHealth() {
    await pollHealth();
    return ctx.health;
  },
  _subs: new Set(),
  onHealth(fn) {
    ctx._subs.add(fn);
    return () => ctx._subs.delete(fn);
  },
};

let engineReady = false;
let healthFails = 0;
let cleanup = null;
let pollTimer = null;

// 라우팅 : #/<route>/<param...>
function parseHash() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  const route = VIEWS[parts[0]] ? parts[0] : 'scenarios';
  return { route, param: parts.slice(1).join('/') || null };
}

function render() {
  if (!engineReady) return;
  const { route, param } = parseHash();
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.route === route);
  if (cleanup) {
    try { cleanup(); } catch { /* 무시 */ }
    cleanup = null;
  }
  $view.scrollTop = 0;
  clear($view);
  cleanup = VIEWS[route].render($view, param, ctx) || null;
}

window.addEventListener('hashchange', render);

// 상단 상태 바
function renderTopbar() {
  const hl = ctx.health;
  const active = hl && hl.active_run;
  $navLive.hidden = !active;
  clear($topbar,
    h('div', { class: 'status-item' },
      h('span', { class: `dot ${hl ? 'ok' : 'bad'}` }),
      hl ? `엔진 v${hl.version}` : '엔진 연결 안 됨'),
    hl && h('div', { class: 'status-item', title: hl.target_alive ? '데모 서버 응답 정상' : '데모 서버 응답 없음' },
      h('span', { class: `dot ${hl.target_alive ? 'ok' : 'bad'}` }),
      '데모 서버 ', h('span', { class: 'mono' }, hl.base_url),
      !hl.target_alive && h('span', { style: { color: 'var(--danger)' } }, ' · 미기동')),
    h('div', { class: 'spacer' }),
    active && h('a', { class: 'run-chip', href: `#/run/${encodeURIComponent(active)}` },
      h('span', { class: 'dot live' }), `실행 중 ${active}`),
  );
}

async function pollHealth() {
  try {
    ctx.health = await api('/health', { timeout: 4000 });
    healthFails = 0;
    if (!$overlay.hidden && $overlay.dataset.kind === 'unreachable') hideOverlay();
  } catch {
    healthFails += 1;
    ctx.health = null;
    // 연속 실패 → 연결 끊김 화면
    if (healthFails >= 2 && engineReady && $overlay.hidden) {
      showOverlay('unreachable', stateView('error', {
        title: '엔진 응답 없음',
        desc: '엔진 서버가 응답하지 않습니다. 엔진을 다시 시작하거나 잠시 후 다시 시도하세요.',
        actions: [restartButton()],
      }));
    }
  }
  renderTopbar();
  for (const fn of ctx._subs) fn(ctx.health);
}

function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(pollHealth, HEALTH_MS);
}

// 오버레이 : 엔진 기동 · 실패 · 종료
function showOverlay(kind, content) {
  $overlay.dataset.kind = kind;
  $overlay.hidden = false;
  clear($overlay, content);
}

function hideOverlay() {
  $overlay.hidden = true;
  $overlay.dataset.kind = '';
  clear($overlay);
}

function restartButton(label = '엔진 다시 시작') {
  return h('button', {
    class: 'btn primary',
    onclick: async () => {
      if (!bridge) return location.reload();
      showOverlay('starting', stateView('loading', { title: '엔진 기동 중', desc: '/health 응답을 기다리는 중…' }));
      applyStatus(await bridge.restart());
    },
  }, label);
}

const FAIL_HINT = {
  missing: 'engine/.venv 가상환경이 있는지 확인하세요. (python -m venv engine/.venv 후 requirements 설치)',
  port: '다른 프로그램이 엔진 포트를 사용 중입니다. 해당 프로세스를 종료하거나 .env의 ENGINE_PORT를 변경하세요.',
  timeout: '엔진 프로세스는 떠 있지만 /health에 응답하지 않습니다. 아래 로그를 확인하세요.',
  exit: '엔진 프로세스가 바로 종료되었습니다. 아래 로그를 확인하세요.',
  spawn: '엔진 실행 파일을 실행할 수 없습니다.',
};

// 배포 모드 : .env · 가상환경 없음
const PACKAGED_HINT = {
  missing: '설치 파일이 손상되었습니다. 앱을 다시 설치하세요.',
  port: '다른 프로그램이 엔진 포트를 사용 중입니다. 해당 프로세스를 종료하거나 ENGINE_PORT 환경변수로 포트를 변경하세요.',
};

function applyStatus(st) {
  if (!st) return;
  ctx.packaged = !!st.packaged;
  $foot.textContent = st.url ? `engine ${st.url.replace('http://', '')}${st.attached ? ' (attached)' : ''}` : 'engine —';
  if (st.state === 'ready') {
    setBase(st.url);
    hideOverlay();
    const first = !engineReady;
    engineReady = true;
    healthFails = 0;
    ctx.health = st.health || ctx.health;
    renderTopbar();
    startPolling();
    if (first) render();
    else pollHealth().then(render);
  } else if (st.state === 'starting') {
    showOverlay('starting', stateView('loading', { title: '엔진 기동 중', desc: `${st.url || ''} /health 응답을 기다리는 중…` }));
  } else if (st.state === 'failed' || st.state === 'stopped') {
    engineReady = st.state === 'stopped' ? engineReady : false;
    ctx.health = null;
    renderTopbar();
    const logs = (st.logs || []).slice(-30).join('\n');
    showOverlay(st.state, stateView('error', {
      title: st.state === 'failed' ? '엔진을 시작하지 못함' : '엔진이 종료됨',
      desc: [st.message, (st.packaged && PACKAGED_HINT[st.reason]) || FAIL_HINT[st.reason]].filter(Boolean).join(' — '),
      detail: logs || null,
      actions: [restartButton(st.state === 'failed' ? '다시 시도' : '엔진 다시 시작')],
    }));
  }
}

async function boot() {
  renderTopbar();
  if (!bridge) {
    // 브라우저 단독 실행 (개발용)
    applyStatus({ state: 'ready', url: 'http://127.0.0.1:5200' });
    return;
  }
  bridge.onStatus(applyStatus);
  applyStatus(await bridge.engine());
}

boot();
