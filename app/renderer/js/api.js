// 엔진 API 클라이언트 : fetch 래퍼 · WebSocket 스트림 · 파일 URL
let base = 'http://127.0.0.1:5200';

export function setBase(url) {
  base = url.replace(/\/$/, '');
}

export function getBase() {
  return base;
}

export class ApiError extends Error {
  constructor(message, { status = 0, kind = 'http', detail = null } = {}) {
    super(message);
    this.status = status;  // 0 = 네트워크
    this.kind = kind;      // network / timeout / http
    this.detail = detail;
  }
}

export async function api(path, { method = 'GET', body, timeout = 10000 } = {}) {
  let res;
  try {
    res = await fetch(base + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeout),
    });
  } catch (e) {
    if (e.name === 'TimeoutError') throw new ApiError(`엔진 응답 시간 초과 (${path})`, { kind: 'timeout' });
    throw new ApiError(`엔진에 연결할 수 없음 (${base})`, { kind: 'network' });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    // 본문 없음
  }
  if (!res.ok) {
    const detail = data && data.detail;
    const msg = typeof detail === 'string' ? detail : `HTTP ${res.status}`;
    throw new ApiError(msg, { status: res.status, detail });
  }
  return data;
}

export async function text(path, { timeout = 10000 } = {}) {
  let res;
  try {
    res = await fetch(base + path, { signal: AbortSignal.timeout(timeout) });
  } catch {
    throw new ApiError(`엔진에 연결할 수 없음 (${base})`, { kind: 'network' });
  }
  if (!res.ok) throw new ApiError(`HTTP ${res.status}`, { status: res.status });
  return res.text();
}

export const encodePath = (p) => String(p).split('/').map(encodeURIComponent).join('/');

// report.json 상대 경로 → /files/<리포트 id>/<경로>
export function fileUrl(reportId, rel) {
  return `${base}/files/${encodePath(reportId)}/${encodePath(rel)}`;
}

export function fileText(reportId, rel) {
  return text(`/files/${encodePath(reportId)}/${encodePath(rel)}`);
}

export function reportHref(reportId) {
  return `#/reports/${encodePath(reportId)}`;
}

// 실행 스트림 : backlog → 실시간 → done 후 서버가 닫음
export function stream(runId, { onEvent, onClose }) {
  const ws = new WebSocket(`${base.replace(/^http/, 'ws')}/runs/${encodeURIComponent(runId)}/stream`);
  let done = false;
  ws.onmessage = (m) => {
    let ev;
    try {
      ev = JSON.parse(m.data);
    } catch {
      return;
    }
    if (ev.event === 'done') done = true;
    onEvent(ev);
  };
  ws.onclose = (e) => onClose && onClose({ done, code: e.code, reason: e.reason });
  return () => {
    ws.onclose = null;
    ws.close();
  };
}
