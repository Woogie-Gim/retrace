// 리포트 화면 : 재현율 게이지 · FE/BE 뱃지 · 스텝 타임라인 · 스텝별 스크린샷 · feature 복사
import { api, encodePath, fileText, fileUrl, reportHref } from '../api.js';
import {
  h, clear, stateView, skeletonList, errorState, gauge, gradeBadge, layerBadge,
  featureCode, fmtRate, fmtTime, toast, PERTURB_LABEL,
} from '../ui.js';

export function render(root, param, ctx) {
  let alive = true;
  if (!param) picker(root, () => alive);
  else detail(root, param, ctx, () => alive);
  return () => { alive = false; };
}

// 리포트 id 없이 진입 : 최근 리포트 목록
function picker(root, isAlive) {
  const body = h('div');
  root.append(h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, '리포트'), h('div', { class: 'sub' }, '확인할 리포트를 선택하세요')),
    h('div', { class: 'actions' }, h('a', { class: 'btn ghost', href: '#/history' }, '히스토리 · 추이 보기'))), body);

  async function load() {
    clear(body, skeletonList(5));
    let list;
    try {
      list = await api('/reports');
    } catch (e) {
      if (isAlive()) clear(body, errorState(e, load));
      return;
    }
    if (!isAlive()) return;
    if (list.length === 0) {
      clear(body, stateView('empty', {
        title: '생성된 리포트 없음',
        desc: '탐색 실행이 최소 재현 스텝을 찾으면 reports/ 폴더에 리포트가 생성되고 여기에 표시됩니다.',
        actions: [h('a', { class: 'btn primary', href: '#/scenarios' }, '첫 실행 시작')],
      }));
      return;
    }
    clear(body, h('div', { class: 'report-picker' }, list.map((r) => h('a', { class: 'sc-item', href: reportHref(r.id) },
      h('div', { class: 'row', style: { justifyContent: 'space-between' } },
        h('span', { class: 'title' }, r.symptom || r.feature || r.name),
        h('span', { class: 'row', style: { gap: '6px' } }, gradeBadge(r.verify.grade, r.verify.rate), layerBadge(r.cause))),
      h('div', { class: 'row', style: { justifyContent: 'space-between' } },
        h('span', { class: 'id' }, r.id), h('span', { class: 'id' }, fmtTime(r.created_at)))))));
  }
  load();
}

function detail(root, id, ctx, isAlive) {
  async function load() {
    clear(root, h('div', { class: 'grid' },
      h('div', { class: 'skeleton', style: { height: '150px' } }),
      h('div', { class: 'report-body' }, skeletonList(6), h('div', { class: 'skeleton', style: { height: '420px' } }))));
    let rep;
    try {
      rep = await api(`/reports/${encodePath(id)}`);
    } catch (e) {
      if (!isAlive()) return;
      if (e.status === 404) {
        clear(root, stateView('empty', {
          title: '리포트를 찾을 수 없음',
          desc: `${id} 에 report.json 이 없습니다. 폴더가 삭제되었거나 실행이 리포트 단계까지 가지 못했을 수 있습니다.`,
          actions: [h('a', { class: 'btn', href: '#/reports' }, '리포트 목록'), h('a', { class: 'btn ghost', href: '#/history' }, '히스토리')],
          fill: true,
        }));
      } else clear(root, errorState(e, load, { fill: true }));
      return;
    }
    if (isAlive()) draw(rep);
  }

  function draw(rep) {
    const ver = rep.verify || {};
    const cause = rep.cause || {};
    const counts = rep.counts || {};
    const ev = rep.evidence || {};
    const steps = rep.steps || [];
    const shots = new Map((ev.screenshots || []).map((s) => [s.index, s]));
    const domHit = (rep.verdicts || []).find((v) => v.kind === 'dom' && v.hit);
    const failedIdx = domHit ? steps.findIndex((s) => domHit.detail.includes(s.text) && /Then|And|But/.test(s.keyword) && !s.perturbation) : -1;
    let selected = steps.findIndex((s) => s.perturbation && s.perturbation !== 'replay');
    if (selected < 0) selected = 0;

    // 헤더
    const header = h('div', { class: 'card report-head' },
      gauge(ver.rate, ver.grade),
      h('div', {},
        h('h1', {}, `[${ver.grade || '-'} ${fmtRate(ver.rate)}] ${rep.symptom || rep.feature}`),
        h('div', { class: 'meta' },
          layerBadge(cause.layer),
          h('span', {}, rep.feature), h('span', { class: 'faint' }, '·'),
          h('span', {}, rep.scenario), h('span', { class: 'faint' }, '·'),
          h('span', {}, fmtTime(rep.created_at)), h('span', { class: 'faint' }, '·'),
          h('span', { class: 'mono' }, rep.id),
          h('span', { class: 'tags' }, (rep.tags || []).map((t) => h('span', { class: 'tag' }, t)))),
        cause.reason && h('div', { class: 'reason' }, `원인 : ${cause.reason}`),
        h('div', { class: 'reason faint' },
          `재현 ${ver.hits ?? '-'}/${ver.runs ?? '-'}회` + (ver.invalid ? ` · 무효 ${ver.invalid}회` : ''))),
      h('div', { class: 'counts' },
        cnt(counts.seed, '시드'), h('span', { class: 'arrow' }, '→'),
        cnt(counts.hit, 'hit'), h('span', { class: 'arrow' }, '→'),
        cnt(counts.minimized, '최소', 'var(--accent)')),
    );

    // 스크린샷 뷰어
    const shotMain = h('div', { class: 'shot-main' });
    const shotCap = h('div', { class: 'shot-caption' });
    const strip = h('div', { class: 'shot-strip' });
    const timeline = h('ol', { class: 'timeline' });

    function img(rel, cls) {
      const el = h('img', { src: fileUrl(rep.id, rel), alt: '', class: cls, loading: 'lazy' });
      el.addEventListener('error', () => el.replaceWith(h('div', { class: 'img-missing' }, h('span', { class: 'mono' }, '⌧'), '이미지를 불러오지 못함')));
      return el;
    }

    function select(i) {
      selected = i;
      for (const li of timeline.children) li.classList.toggle('selected', Number(li.dataset.i) === i);
      for (const t of strip.children) t.classList.toggle('selected', Number(t.dataset.i) === i);
      const s = steps[i];
      const shot = shots.get(i);
      clear(shotMain, shot ? img(shot.path) : h('div', { class: 'img-missing' }, h('span', { class: 'mono' }, '∅'), '이 스텝의 스크린샷 없음'));
      clear(shotCap,
        h('span', { class: 'faint' }, String(i + 1).padStart(2, '0')),
        s && s.perturbation && h('span', { class: `ptag${s.perturbation === 'replay' ? ' replay' : ''}` }, `⚡ ${PERTURB_LABEL[s.perturbation] || s.perturbation}`),
        h('span', {}, s ? `${s.keyword} ${s.text}` : ''));
    }

    steps.forEach((s, i) => {
      const cls = [s.background && 'bg', s.perturbation && 'perturb', i === failedIdx && 'failed'].filter(Boolean).join(' ');
      timeline.append(h('li', { class: cls, 'data-i': i, onclick: () => select(i), title: s.perturbation ? '탐색으로 찾은 교란 스텝' : '' },
        h('span', { class: 'idx' }, String(i + 1).padStart(2, '0')),
        h('span', { class: 'kw' }, s.perturbation && s.perturbation !== 'replay' ? '⚡ ' + s.keyword : s.keyword),
        h('span', { class: 'txt' }, s.text,
          s.perturbation && h('span', { class: `ptag${s.perturbation === 'replay' ? ' replay' : ''}` }, PERTURB_LABEL[s.perturbation] || s.perturbation),
          s.background && h('span', { class: 'faint', style: { marginLeft: '8px', fontSize: '11px' } }, '사전 조건'),
          i === failedIdx && h('span', { style: { marginLeft: '8px', fontSize: '11px' } }, '✕ 실패'))));
      if (shots.has(i)) {
        strip.append(h('button', { class: `thumb${s.perturbation ? ' perturb' : ''}`, 'data-i': i, onclick: () => select(i) },
          img(shots.get(i).path), h('span', { class: 'n' }, String(i + 1).padStart(2, '0'))));
      }
    });

    // feature
    const featureBody = h('div', {}, h('div', { class: 'card-body' }, h('div', { class: 'skeleton', style: { height: '160px' } })));
    let featureText = null;
    const copyBtn = h('button', {
      class: 'btn sm', disabled: true,
      onclick: async () => {
        try {
          if (window.retrace) await window.retrace.copy(featureText);
          else await navigator.clipboard.writeText(featureText);
          toast('repro.feature 복사됨');
        } catch {
          toast('복사 실패', 'error');
        }
      },
    }, '⧉ feature 복사');
    fileText(rep.id, 'repro.feature').then((t) => {
      featureText = t;
      copyBtn.disabled = false;
      clear(featureBody, featureCode(t));
    }).catch((e) => {
      clear(featureBody, h('div', { class: 'card-body' }, stateView('error', {
        title: 'repro.feature 를 불러오지 못함', desc: e.message,
      })));
    });

    const evidenceWarn = ev.status && ev.status !== 'hit' && h('div', { class: 'inline-alert warn' },
      h('span', {}, '⚠'), h('div', {}, `증거 run이 ${ev.tries}회 시도 동안 증상을 다시 재현하지 못했습니다 (${ev.status}). 스크린샷은 마지막 시도 기준입니다.`));

    const env = rep.environment || {};
    clear(root,
      h('div', { class: 'page-head' },
        h('div', {}, h('a', { href: '#/reports', class: 'dim', style: { fontSize: '12px' } }, '← 리포트 목록')),
        h('div', { class: 'actions' },
          h('a', { class: 'btn sm ghost', href: fileUrl(rep.id, 'report.md'), target: '_blank' }, 'report.md'),
          ev.console && h('a', { class: 'btn sm ghost', href: fileUrl(rep.id, ev.console), target: '_blank' }, '콘솔 로그'),
          ev.network && h('a', { class: 'btn sm ghost', href: fileUrl(rep.id, ev.network), target: '_blank' }, '네트워크 로그'))),
      h('div', { class: 'grid' },
        header,
        evidenceWarn,
        h('div', { class: 'report-body' },
          h('div', { class: 'grid' },
            h('div', { class: 'card' },
              h('div', { class: 'card-head' }, '재현 스텝', h('span', { class: 'right' },
                h('span', { class: 'ptag' }, '⚡ 교란'), h('span', { class: 'dim', style: { marginLeft: '6px' } }, '탐색으로 찾은 스텝'))),
              steps.length ? timeline : h('div', { class: 'card-body' }, stateView('empty', { title: '스텝 없음' }))),
            h('div', { class: 'card card-body result-pair' },
              h('div', { class: 'box' }, h('div', { class: 'h' }, '기대 결과'), h('div', { class: 'v' }, rep.expected || '-')),
              h('div', { class: 'box actual' }, h('div', { class: 'h' }, '실제 결과'), h('div', { class: 'v' }, rep.actual || '-'))),
            h('div', { class: 'card' },
              h('div', { class: 'card-head' }, '오라클 판정'),
              h('div', { class: 'card-body verdicts' }, (rep.verdicts || []).length
                ? rep.verdicts.map((v) => h('div', { class: `verdict${v.hit ? ' hit' : ''}` },
                  h('span', { class: 'k' }, h('span', { class: `dot ${v.hit ? 'bad' : 'ok'}` }), v.kind),
                  h('span', { class: 'd' }, v.detail)))
                : h('span', { class: 'dim' }, '판정 기록 없음'))),
            h('div', { class: 'card' },
              h('div', { class: 'card-head' }, '환경'),
              h('dl', { class: 'card-body kv' },
                h('dt', {}, '브라우저'), h('dd', { class: 'mono' }, env.browser || '-'),
                h('dt', {}, '창 크기'), h('dd', { class: 'mono' }, env.window || '-'),
                h('dt', {}, '네트워크'), h('dd', { class: 'mono' }, env.network || '-'),
                h('dt', {}, '증거 run'), h('dd', { class: 'mono' }, `${ev.status || '-'} (${ev.tries ?? '-'}회)`),
                rep.generated && [h('dt', {}, '회귀 테스트'), h('dd', { class: 'mono' }, rep.generated)]))),
          h('div', { class: 'grid' },
            h('div', { class: 'card', style: { overflow: 'hidden' } },
              h('div', { class: 'card-head' }, '스텝별 스크린샷', h('span', { class: 'right mono' }, `${shots.size}장`)),
              shots.size
                ? [shotMain, shotCap, strip]
                : h('div', { class: 'card-body' }, stateView('empty', { title: '스크린샷 없음', desc: '증거 run에서 저장된 스크린샷이 없습니다.' }))),
            h('div', { class: 'card' },
              h('div', { class: 'card-head' }, 'repro.feature', h('span', { class: 'right' }, copyBtn)),
              featureBody)),
        ),
      ));
    if (steps.length) select(selected);
  }

  load();
}

function cnt(n, label, color) {
  return h('div', {}, h('div', { class: 'n', style: color ? { color } : undefined }, n ?? '-'), h('span', { class: 'lbl' }, label));
}
