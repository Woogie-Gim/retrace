// 실행 화면 : 단계별 진행률 · 카운터 · 실시간 로그 · 종료 결과
// /runs 는 메모리 기반이라 현재(이번 엔진 세션) 실행 표시에만 사용
import { api, stream, reportHref } from '../api.js';
import { h, clear, stateView, errorState, gradeBadge, layerBadge, fmtClock, fmtRate, fmtTime, PERTURB_LABEL } from '../ui.js';

const PHASES = [
  { key: 'explore', name: '탐색' },
  { key: 'minimize', name: '최소화' },
  { key: 'verify', name: '검증' },
  { key: 'report', name: '리포트' },
];
const STATUS = {
  running: ['실행 중', 'running'], ok: ['완료', 'ok'], no_hit: ['재현 실패', 'warn'],
  not_reproduced: ['최소화 미재현', 'warn'], error: ['오류', 'error'],
};
const MAX_LINES = 2000;

export function render(root, param, ctx) {
  let alive = true;
  let closeWs = null;
  let tick = null;

  async function resolveId() {
    if (param) return param;
    const active = ctx.health && ctx.health.active_run;
    if (active) return active;
    if (ctx.lastRunId) return ctx.lastRunId;
    // 이번 엔진 세션의 최근 실행
    const runs = await api('/runs');
    return runs.length ? runs[0].id : null;
  }

  async function load() {
    clear(root, stateView('loading', { title: '실행 정보를 불러오는 중', fill: true }));
    let id;
    let info;
    try {
      id = await resolveId();
      if (id) info = await api(`/runs/${encodeURIComponent(id)}`);
    } catch (e) {
      if (!alive) return;
      if (e.status === 404) {
        clear(root, stateView('empty', {
          title: '실행 정보 없음',
          desc: `${id} 실행 기록이 엔진 메모리에 없습니다. 엔진이 재시작되면 진행 기록은 사라지며, 완료된 결과는 히스토리에서 확인할 수 있습니다.`,
          actions: [h('a', { class: 'btn', href: '#/history' }, '히스토리 보기'), h('a', { class: 'btn ghost', href: '#/scenarios' }, '새 실행')],
          fill: true,
        }));
      } else clear(root, errorState(e, load, { fill: true }));
      return;
    }
    if (!alive) return;
    if (!id) {
      clear(root, stateView('empty', {
        title: '진행 중인 실행 없음',
        desc: '시나리오 화면에서 시드를 고르고 탐색을 실행하면 진행 상황이 여기에 실시간으로 표시됩니다.',
        actions: [h('a', { class: 'btn primary', href: '#/scenarios' }, '시나리오 선택'), h('a', { class: 'btn ghost', href: '#/history' }, '히스토리')],
        fill: true,
      }));
      return;
    }
    ctx.lastRunId = id;
    mount(info);
  }

  function mount(info) {
    const o = info.options || {};
    const st = {
      phase: null, done: new Set(), candidates: 0, started: 0, runs: 0, maxRuns: o.max_runs || 0,
      hits: 0, mini: { from: 0, size: 0, probes: 0 }, verify: { trial: 0, total: o.verify_n || 0, hits: 0 },
      evidence: { trial: 0, total: o.tries || 0 }, t0: null, t1: null, result: null, error: null, lastSeq: -1,
    };

    const statusBadge = h('span');
    const phaseEls = PHASES.map((p, i) => {
      const el = h('div', { class: 'phase' },
        h('div', { class: 'name' }, h('span', { class: 'num' }, `0${i + 1}`), p.name),
        h('div', { class: 'bar' }, h('i')),
        h('div', { class: 'meta' }, '대기'));
      return { ...p, el, bar: el.querySelector('.bar'), fill: el.querySelector('.bar > i'), meta: el.querySelector('.meta') };
    });
    const stat = (label, cls = '') => {
      const v = h('div', { class: 'value' }, '0');
      return { el: h('div', { class: `card stat ${cls}` }, h('div', { class: 'label' }, label), v), v };
    };
    const sCand = stat('시도 후보');
    const sRuns = stat('실행');
    const sHits = stat('hit', 'hit');
    const sTime = stat('경과 시간');
    const mainBar = h('div', { class: 'bar main' }, h('i'));
    const logEl = h('div', { class: 'console' }, h('div', { class: 'empty' }, '이벤트 대기 중…'));
    const logCount = h('span', { class: 'right mono' }, '0');
    const resultEl = h('div', { class: 'slot' });
    const connEl = h('div', { class: 'slot' });

    clear(root,
      h('div', { class: 'page-head' },
        h('div', {},
          h('h1', { class: 'mono', style: { fontSize: '18px' } }, info.id),
          h('div', { class: 'sub' }, `${info.scenario} · 시작 ${fmtTime(info.created_at)} · k=${o.k} · max_runs=${o.max_runs} · verify ${o.verify_n}회`)),
        h('div', { class: 'actions' }, statusBadge)),
      h('div', { class: 'grid' },
        resultEl,
        connEl,
        h('div', { class: 'card card-body', style: { display: 'grid', gap: '14px' } },
          h('div', { class: 'row', style: { justifyContent: 'space-between', fontSize: '12px' } },
            h('span', { class: 'dim' }, '전체 진행률'), h('span', { class: 'mono dim', id: 'pct' }, '0%')),
          mainBar,
          h('div', { class: 'phases' }, phaseEls.map((p) => p.el))),
        h('div', { class: 'stats' }, sCand.el, sRuns.el, sHits.el, sTime.el),
        h('div', { class: 'card' },
          h('div', { class: 'card-head' }, '실시간 로그', logCount),
          logEl),
      ));
    const pctEl = root.querySelector('#pct');

    // 렌더
    function setBadge(status) {
      const [label, cls] = STATUS[status] || [status, 'warn'];
      clear(statusBadge, h('span', { class: `badge status-${cls}` }, status === 'running' && h('span', { class: 'dot live', style: { width: '6px', height: '6px' } }), label));
    }

    function phaseProgress(key) {
      if (st.done.has(key)) return 1;
      if (key !== st.phase) return 0;
      if (key === 'explore') return st.maxRuns ? Math.min(1, st.runs / st.maxRuns) : 0;
      if (key === 'verify') return st.verify.total ? st.verify.trial / st.verify.total : 0;
      if (key === 'report') return st.evidence.total ? st.evidence.trial / st.evidence.total : 0;
      return null;  // 최소화 : 진행률 산정 불가 → indeterminate
    }

    function paint() {
      let total = 0;
      for (const p of phaseEls) {
        const v = phaseProgress(p.key);
        const active = p.key === st.phase && !st.done.has(p.key) && !st.result;
        p.el.classList.toggle('active', active);
        p.el.classList.toggle('done', st.done.has(p.key));
        p.bar.classList.toggle('indet', active && v === null);
        p.fill.style.width = `${Math.round((v || 0) * 100)}%`;
        total += v === null ? 0.5 : v;
        p.meta.textContent = phaseMeta(p.key);
      }
      const pct = st.result && st.result.status === 'ok' ? 100 : Math.round((total / PHASES.length) * 100);
      mainBar.firstChild.style.width = `${pct}%`;
      pctEl.textContent = `${pct}%`;
      sCand.v.replaceChildren(String(st.started), h('small', {}, st.candidates ? ` / ${st.candidates}` : ''));
      sRuns.v.replaceChildren(String(st.runs), h('small', {}, st.maxRuns ? ` / ${st.maxRuns}` : ''));
      sHits.v.textContent = String(st.hits);
      paintTime();
    }

    function phaseMeta(key) {
      const seen = st.done.has(key) || st.phase === key;
      if (!seen) return st.result ? '건너뜀' : '대기';
      if (key === 'explore') return `run ${st.runs}/${st.maxRuns} · 후보 ${st.started}/${st.candidates}`;
      if (key === 'minimize') return `스텝 ${st.mini.from} → ${st.mini.size || st.mini.from} · probe ${st.mini.probes}`;
      if (key === 'verify') return `${st.verify.trial}/${st.verify.total} · hit ${st.verify.hits}`;
      return `증거 run ${st.evidence.trial}/${st.evidence.total}`;
    }

    function paintTime() {
      if (st.t0 === null) return;
      const end = st.t1 ?? Date.now() / 1000;
      const sec = Math.max(0, Math.round(end - st.t0));
      sTime.v.textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
    }

    let lines = 0;
    function log(ev, cls, msg) {
      if (lines === 0) logEl.replaceChildren();
      const stick = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
      logEl.append(h('div', { class: `line ${cls}` },
        h('span', { class: 't' }, fmtClock(ev.ts)), h('span', { class: 'ev' }, ev.event), h('span', { class: 'msg' }, msg)));
      lines += 1;
      if (logEl.childElementCount > MAX_LINES) logEl.firstChild.remove();
      logCount.textContent = String(lines);
      if (stick) logEl.scrollTop = logEl.scrollHeight;
    }

    const candLabel = (c) => {
      const ins = (c.steps || []).filter((s) => s.perturbation && s.perturbation !== 'replay').map((s) => s.text).join(' + ');
      return `#${c.index} [${PERTURB_LABEL[c.kind] || c.kind}] @${c.position} ${ins}`;
    };

    function finishPhase() {
      if (st.phase) st.done.add(st.phase);
    }

    function apply(ev) {
      if (ev.seq <= st.lastSeq) return;  // 재연결 시 backlog 중복 제거
      st.lastSeq = ev.seq;
      if (st.t0 === null) st.t0 = ev.ts;
      const d = ev.data || {};
      switch (ev.event) {
        case 'run_start':
          log(ev, 'muted', `실행 시작 · ${d.scenario}`);
          break;
        case 'phase': {
          finishPhase();
          st.phase = d.phase;
          if (d.phase === 'explore') { st.candidates = d.candidates; st.maxRuns = d.max_runs; }
          if (d.phase === 'minimize') { st.mini.from = d.steps; st.mini.size = d.steps; }
          if (d.phase === 'verify') st.verify.total = d.total;
          if (d.phase === 'report') st.evidence.total = d.tries;
          const name = PHASES.find((p) => p.key === d.phase)?.name || d.phase;
          const extra = { explore: `후보 ${d.candidates}개 · 예산 ${d.max_runs}회`, minimize: `스텝 ${d.steps}개`, verify: `${d.total}회 반복`, report: `증거 run 최대 ${d.tries}회` }[d.phase];
          log(ev, 'phase', `▸ ${name}${extra ? ` (${extra})` : ''}`);
          break;
        }
        case 'baseline_start':
          log(ev, 'muted', 'baseline 실행 (교란 없음)');
          break;
        case 'candidate_start':
          st.started += 1;
          log(ev, '', `후보 ${candLabel(d.candidate)}`);
          break;
        case 'run_done':
          st.runs = d.runs ?? st.runs + 1;
          log(ev, d.status === 'hit' ? 'hit' : 'muted', `${d.candidate < 0 ? 'baseline' : `후보 #${d.candidate}`} trial ${d.trial + 1} → ${d.status}  (${st.runs}/${d.max_runs ?? st.maxRuns})`);
          break;
        case 'hit': {
          st.hits += 1;
          const why = (d.verdicts || []).filter((v) => v.hit).map((v) => `${v.kind}: ${v.detail}`).join(' / ');
          log(ev, 'hit', `HIT ${candLabel(d.candidate)}  ${d.hits}/${d.trials}${why ? `\n${why}` : ''}`);
          break;
        }
        case 'minimize_step':
          st.mini.probes += 1;
          if (d.record.outcome === 'hit') st.mini.size = Math.min(st.mini.size || d.size, d.size);
          log(ev, d.record.outcome === 'hit' ? 'hit' : 'muted', `ddmin 스텝 ${d.size}개 → ${d.record.outcome} (run ${d.record.runs})${d.record.detail ? ` · ${d.record.detail}` : ''}`);
          break;
        case 'verify_progress':
          st.verify.trial = d.trial + 1;
          st.verify.total = d.total;
          if (d.status === 'hit') st.verify.hits += 1;
          log(ev, d.status === 'hit' ? 'hit' : 'muted', `검증 ${d.trial + 1}/${d.total} → ${d.status}${d.detail ? ` · ${d.detail}` : ''}`);
          break;
        case 'evidence_run':
          st.evidence.trial = d.trial + 1;
          st.evidence.total = d.total;
          log(ev, d.status === 'hit' ? 'hit' : 'muted', `증거 run ${d.trial + 1}/${d.total} → ${d.status}`);
          break;
        case 'error':
          st.error = d;
          log(ev, 'error', d.message);
          break;
        case 'done':
          if (d.status === 'ok') finishPhase();
          st.result = d;
          st.t1 = ev.ts;
          log(ev, d.status === 'ok' ? 'done' : 'error', doneText(d));
          showResult();
          ctx.refreshHealth();
          break;
        default:
          log(ev, 'muted', JSON.stringify(d));
      }
      setBadge(st.result ? st.result.status : 'running');
      paint();
    }

    function doneText(d) {
      if (d.status === 'ok') return `완료 · ${d.grade} ${fmtRate(d.rate)} · ${d.cause} · ${d.report_id}`;
      if (d.status === 'no_hit') return `종료 · 예산 내 재현 실패 (${d.stopped}, run ${d.runs})`;
      if (d.status === 'not_reproduced') return `종료 · 최소화 중 재현 안 됨 (${d.stopped})`;
      return `오류 · ${d.message || '알 수 없는 오류'}`;
    }

    function showResult() {
      const d = st.result;
      if (d.status === 'ok') {
        const c = d.counts || {};
        clear(resultEl, h('div', { class: 'card result-card', style: { borderColor: 'var(--accent-line)' } },
          h('div', { class: 'text' },
            h('div', { class: 'title' }, '최소 재현 스텝 확보'),
            h('div', { class: 'dim', style: { fontSize: '13px' } },
              `시드 ${c.seed ?? '-'} → hit ${c.hit ?? '-'} → 최소 ${c.minimized ?? '-'} 스텝 · `, h('span', { class: 'mono' }, d.report_id))),
          gradeBadge(d.grade, d.rate), layerBadge(d.cause),
          h('a', { class: 'btn primary', href: reportHref(d.report_id) }, '리포트 보기 →')));
      } else if (d.status === 'error') {
        clear(resultEl, stateView('error', {
          title: '실행 실패',
          desc: d.message || (st.error && st.error.message) || '알 수 없는 오류',
          detail: st.error && st.error.traceback,
          actions: [h('a', { class: 'btn', href: '#/scenarios' }, '시나리오로 돌아가기')],
        }));
      } else {
        const noHit = d.status === 'no_hit';
        clear(resultEl, stateView('empty', {
          title: noHit ? '예산 안에서 증상을 재현하지 못함' : '최소화 과정에서 재현되지 않음',
          desc: noHit
            ? `run ${d.runs}회 동안 오라클이 hit을 판정하지 않았습니다 (${d.stopped}). 오라클 태그를 바꾸거나 max_runs · k 를 늘려 다시 시도해 보세요.`
            : `hit 시퀀스가 재실행에서 재현되지 않았습니다 (${d.stopped}). 확률성 버그라면 k 를 늘려 다시 시도해 보세요.`,
          actions: [h('a', { class: 'btn primary', href: '#/scenarios' }, '옵션 바꿔 다시 실행')],
        }));
      }
    }

    function connect() {
      clear(connEl);
      closeWs = stream(info.id, {
        onEvent: (ev) => alive && apply(ev),
        onClose: ({ done }) => {
          closeWs = null;
          if (!alive || done || st.result) return;
          clear(connEl, h('div', { class: 'inline-alert error' },
            h('span', {}, '✕'),
            h('div', { style: { flex: 1 } }, '진행 스트림 연결이 끊겼습니다. 엔진 상태를 확인한 뒤 다시 연결하세요.'),
            h('button', { class: 'btn sm', onclick: connect }, '다시 연결')));
        },
      });
    }

    setBadge(info.status);
    paint();
    connect();
    tick = setInterval(() => !st.result && paintTime(), 1000);
  }

  load();
  return () => {
    alive = false;
    clearInterval(tick);
    if (closeWs) closeWs();
  };
}
