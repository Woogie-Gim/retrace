// UI 헬퍼 : 엘리먼트 생성 · 상태 화면 · 뱃지 · 게이지 · 포맷
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

const SVG_NS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const c of children.flat()) if (c) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

// 상태 화면 : empty / loading / error
const STATE_ICON = { empty: '∅', loading: null, error: '!' };

export function stateView(kind, { title, desc, detail, actions = [], fill = false } = {}) {
  return h('div', { class: `state ${kind}${fill ? ' fill' : ''}`, role: kind === 'error' ? 'alert' : 'status' },
    kind === 'loading' ? h('div', { class: 'spinner' }) : h('div', { class: 'state-icon' }, STATE_ICON[kind]),
    title && h('div', { class: 'state-title' }, title),
    desc && h('div', { class: 'state-desc' }, desc),
    detail && h('pre', { class: 'state-detail' }, detail),
    actions.length > 0 && h('div', { class: 'state-actions' }, actions),
  );
}

export function skeletonList(n = 4) {
  return h('div', { class: 'skeleton-list' }, Array.from({ length: n }, () => h('div', { class: 'skeleton' })));
}

export function errorState(err, retry, extra = {}) {
  const network = err && (err.kind === 'network' || err.kind === 'timeout');
  return stateView('error', {
    title: extra.title || (network ? '엔진에 연결할 수 없음' : '데이터를 불러오지 못함'),
    desc: err ? err.message : '알 수 없는 오류',
    detail: extra.detail,
    actions: retry ? [h('button', { class: 'btn', onclick: retry }, '다시 시도')] : [],
    fill: extra.fill,
  });
}

// 등급 · 계층
const GRADE_CLASS = { 확정: 'confirmed', 간헐: 'intermittent', 희귀: 'rare', 미재현: 'none', 판정불가: 'none' };

export function gradeClass(grade) {
  return GRADE_CLASS[grade] || 'none';
}

export function gradeColor(grade) {
  return `var(--grade-${gradeClass(grade)})`;
}

export function gradeBadge(grade, rate) {
  const label = rate === null || rate === undefined ? (grade || '-') : `${grade || '-'} ${fmtRate(rate)}`;
  return h('span', { class: `badge grade-${gradeClass(grade)}` }, label);
}

export function layerBadge(layer) {
  const cls = layer === 'FE' || layer === 'BE' ? layer : 'unknown';
  return h('span', { class: `badge layer-${cls}`, title: '원인 계층' }, layer || '미분류');
}

export function gauge(rate, grade, size = 112) {
  const r = size / 2 - 8;
  const c = 2 * Math.PI * r;
  const v = rate === null || rate === undefined ? 0 : Math.max(0, Math.min(1, rate));
  const color = gradeColor(grade);
  return h('div', { class: 'gauge', style: { width: `${size}px`, height: `${size}px` } },
    s('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}` },
      s('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--surface-3)', 'stroke-width': 8 }),
      s('circle', {
        cx: size / 2, cy: size / 2, r, fill: 'none', stroke: color, 'stroke-width': 8,
        'stroke-linecap': 'round', 'stroke-dasharray': `${c * v} ${c}`,
      }),
    ),
    h('div', { class: 'center' },
      h('div', { class: 'pct' }, fmtRate(rate)),
      h('div', { class: 'grade', style: { color } }, grade || '-'),
    ),
  );
}

// 포맷
export function fmtRate(rate) {
  return rate === null || rate === undefined ? '-' : `${Math.round(rate * 100)}%`;
}

export function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtClock(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// 교란 종류 라벨
export const PERTURB_LABEL = {
  rapid_click: '연타', back: '뒤로가기', refresh: '새로고침', network: '네트워크',
  resize: '창 크기', boundary: '경계값', replay: '재실행',
};

// feature 소스 하이라이트 (줄 단위)
const KW = /^(\s*)(Feature|Background|Scenario Outline|Scenario|Given|When|Then|And|But|Examples)(:?)(.*)$/;

export function featureCode(source) {
  const pre = h('pre', { class: 'code' });
  for (const line of String(source || '').replace(/\r/g, '').replace(/\n$/, '').split('\n')) {
    const span = h('span', { class: 'ln' });
    const t = line.trim();
    if (t.startsWith('#')) span.append(h('span', { class: 'cmt' }, line));
    else if (t.startsWith('@')) span.append(h('span', { class: 'tagc' }, line));
    else {
      const m = line.match(KW);
      if (m) {
        const headKw = /^(Feature|Background|Scenario)/.test(m[2]);
        span.append(m[1], h('span', { class: 'kw' }, m[2] + m[3]));
        span.append(headKw ? h('span', { class: 'head' }, m[4]) : strings(m[4]));
      } else span.append(line || ' ');
    }
    pre.append(span);
  }
  return pre;
}

function strings(text) {
  // "..." 문자열 강조
  const frag = document.createDocumentFragment();
  let last = 0;
  for (const m of text.matchAll(/"[^"]*"/g)) {
    frag.append(text.slice(last, m.index), h('span', { class: 'str' }, m[0]));
    last = m.index + m[0].length;
  }
  frag.append(text.slice(last));
  return frag;
}

// 토스트
export function toast(message, kind = 'ok', ms = 2400) {
  const el = h('div', { class: `toast ${kind}` }, message);
  document.getElementById('toasts').append(el);
  setTimeout(() => el.remove(), ms);
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}
