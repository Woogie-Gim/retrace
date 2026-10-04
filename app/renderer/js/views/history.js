// 히스토리 화면 : /reports (파일 기반) 과거 실행 목록 + 시나리오별 재현율 추이
// 진행 중 실행은 /runs 로 배너만 표시
import { api, reportHref } from '../api.js';
import { h, s, clear, stateView, skeletonList, errorState, gradeBadge, gradeColor, layerBadge, fmtRate, fmtTime } from '../ui.js';

const PALETTE = ['#2dd4bf', '#f59e0b', '#a855f7', '#3b82f6', '#f472b6', '#84cc16', '#f05252', '#94a3b8'];

const memo = { hidden: new Set() };

export function render(root, _param, ctx) {
  let alive = true;
  const banner = h('div');
  const body = h('div');
  const countEl = h('div', { class: 'sub' }, '과거 실행 결과');
  root.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', {}, '히스토리'), countEl),
      h('div', { class: 'actions' }, h('button', { class: 'btn sm', onclick: () => load() }, '↻ 새로고침'))),
    banner, body);

  async function loadLive() {
    // 현재 실행 상태 (메모리 기반 /runs)
    try {
      const running = (await api('/runs')).filter((r) => r.status === 'running');
      if (!alive) return;
      clear(banner, running.map((r) => h('div', { class: 'live-banner' },
        h('span', { class: 'dot live' }), h('span', {}, '실행 중'),
        h('span', { class: 'mono' }, r.id), h('span', { class: 'dim' }, r.scenario),
        h('a', { class: 'btn sm', href: `#/run/${encodeURIComponent(r.id)}`, style: { marginLeft: 'auto' } }, '진행 보기'))));
    } catch {
      clear(banner);
    }
  }

  async function load() {
    loadLive();
    clear(body, h('div', { class: 'grid' }, h('div', { class: 'skeleton', style: { height: '260px' } }), skeletonList(5)));
    let list;
    try {
      list = await api('/reports');
    } catch (e) {
      if (alive) clear(body, errorState(e, load));
      return;
    }
    if (!alive) return;
    countEl.textContent = `리포트 ${list.length}건 · reports/ 폴더 기준`;
    if (list.length === 0) {
      clear(body, stateView('empty', {
        title: '실행 기록 없음',
        desc: '완료된 탐색 실행의 리포트(reports/<실행>/<시나리오>/report.json)가 여기에 쌓입니다.',
        actions: [h('a', { class: 'btn primary', href: '#/scenarios' }, '첫 실행 시작')],
      }));
      return;
    }
    draw(list);
  }

  function draw(list) {
    const names = [...new Set(list.map((r) => r.name))].sort();
    const color = Object.fromEntries(names.map((n, i) => [n, PALETTE[i % PALETTE.length]]));
    const visible = list.filter((r) => !memo.hidden.has(r.name));

    const legend = h('div', { class: 'legend' }, names.map((n) => h('button', {
      class: memo.hidden.has(n) ? '' : 'on',
      onclick: () => {
        if (memo.hidden.has(n)) memo.hidden.delete(n); else memo.hidden.add(n);
        draw(list);
      },
    }, h('span', { class: 'sw', style: { background: color[n] } }), n)));

    clear(body, h('div', { class: 'grid' },
      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, '재현율 추이', h('span', { class: 'right' }, legend)),
        h('div', { class: 'trend' }, trend(visible, color))),
      h('div', { class: 'card' },
        visible.length
          ? h('table', { class: 'table' },
            h('thead', {}, h('tr', {},
              ['시각', '시나리오', '증상', '등급', '재현율', '원인', '스텝 (시드→최소)', 'id'].map((t) => h('th', {}, t)))),
            h('tbody', {}, visible.map((r) => h('tr', { onclick: () => ctx.navigate(reportHref(r.id)) },
              h('td', { class: 'mono' }, fmtTime(r.created_at)),
              h('td', {}, h('span', { class: 'row', style: { gap: '8px' } },
                h('span', { class: 'sw', style: { width: '8px', height: '8px', borderRadius: '2px', background: color[r.name] } }),
                h('span', { class: 'mono' }, r.name))),
              h('td', { class: 'dim' }, r.symptom || r.feature || '-'),
              h('td', {}, gradeBadge(r.verify.grade)),
              h('td', {}, h('div', { class: 'rate-cell' },
                h('div', { class: 'bar' }, h('i', { style: { width: `${Math.round((r.verify.rate || 0) * 100)}%`, background: gradeColor(r.verify.grade) } })),
                fmtRate(r.verify.rate))),
              h('td', {}, layerBadge(r.cause)),
              h('td', { class: 'mono' }, r.counts ? `${r.counts.seed ?? '-'} → ${r.counts.minimized ?? '-'}` : '-'),
              h('td', { class: 'mono faint' }, r.id.split('/')[0])))))
          : h('div', { class: 'card-body' }, stateView('empty', { title: '표시할 시나리오 없음', desc: '범례에서 시나리오를 하나 이상 켜세요.' })),
      )));
  }

  load();
  const timer = setInterval(loadLive, 5000);
  return () => { alive = false; clearInterval(timer); };
}

// 시나리오별 rate 라인 (x = 생성 시각)
function trend(list, color) {
  const pts = list
    .filter((r) => r.verify.rate !== null && r.verify.rate !== undefined && r.created_at)
    .map((r) => ({ ...r, t: new Date(r.created_at).getTime() }))
    .filter((r) => !Number.isNaN(r.t))
    .sort((a, b) => a.t - b.t);
  if (pts.length === 0) {
    return stateView('empty', { title: '추이 데이터 없음', desc: '재현율이 기록된 리포트가 없습니다.' });
  }
  const W = 1000;
  const H = 220;
  const pad = { l: 44, r: 16, t: 12, b: 28 };
  const t0 = pts[0].t;
  const t1 = pts[pts.length - 1].t;
  const x = (t) => (t1 === t0 ? (pad.l + W - pad.r) / 2 : pad.l + ((t - t0) / (t1 - t0)) * (W - pad.l - pad.r));
  const y = (v) => pad.t + (1 - v) * (H - pad.t - pad.b);

  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' });
  for (const v of [0, 0.3, 1]) {
    // 등급 경계선 (30% 간헐 · 100% 확정)
    svg.append(s('line', { class: v === 0 ? 'axis' : 'grid-line', x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
    svg.append(s('text', { class: 'lbl', x: pad.l - 8, y: y(v) + 3, 'text-anchor': 'end' }, `${v * 100}%`));
  }
  svg.append(s('text', { class: 'lbl', x: pad.l, y: H - 6 }, fmtTime(pts[0].created_at)));
  if (t1 !== t0) svg.append(s('text', { class: 'lbl', x: W - pad.r, y: H - 6, 'text-anchor': 'end' }, fmtTime(pts[pts.length - 1].created_at)));

  const groups = new Map();
  for (const p of pts) {
    if (!groups.has(p.name)) groups.set(p.name, []);
    groups.get(p.name).push(p);
  }
  for (const [name, g] of groups) {
    if (g.length > 1) {
      svg.append(s('polyline', {
        class: 'series', stroke: color[name], 'vector-effect': 'non-scaling-stroke',
        points: g.map((p) => `${x(p.t)},${y(p.verify.rate)}`).join(' '),
      }));
    }
  }
  // 점은 HTML 오버레이 (preserveAspectRatio=none 에서 원 왜곡 방지)
  const wrap = h('div', { style: { position: 'relative' } }, svg);
  for (const p of pts) {
    wrap.append(h('a', {
      href: reportHref(p.id),
      title: `${p.name} · ${fmtRate(p.verify.rate)} ${p.verify.grade || ''} · ${fmtTime(p.created_at)}`,
      style: {
        position: 'absolute', left: `${(x(p.t) / W) * 100}%`, top: `${(y(p.verify.rate) / H) * 100}%`,
        width: '10px', height: '10px', margin: '-5px 0 0 -5px', borderRadius: '50%',
        background: color[p.name], border: '2px solid var(--surface)',
      },
    }));
  }
  return wrap;
}
