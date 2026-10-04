// 시나리오 화면 : 시드 목록 · feature 미리보기 · 오라클 태그 토글 · 실행 시작
import { api } from '../api.js';
import { h, clear, stateView, skeletonList, errorState, featureCode, toast } from '../ui.js';

const ORACLES = [
  { tag: '@oracle-api', name: 'api', desc: '화면 값 ↔ API 값 대조' },
  { tag: '@oracle-console', name: 'console', desc: 'SEVERE 콘솔 에러' },
  { tag: '@oracle-network', name: 'network', desc: '4xx · 5xx 응답' },
];
const ORACLE_TAGS = new Set(ORACLES.map((o) => o.tag));

const DEFAULTS = { k: 3, max_runs: 60, verify_n: 10, tries: 10, headed: false, copy_generated: false };

// 탭 이동 후에도 선택·설정 유지
const memo = { selected: null, tags: {}, options: { ...DEFAULTS } };

export function render(root, _param, ctx) {
  let alive = true;
  let items = [];

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, '시나리오'), h('div', { class: 'sub' }, '시드 시나리오를 골라 교란 탐색을 실행합니다')));
  const body = h('div');
  root.append(head, body);

  async function load() {
    clear(body, h('div', { class: 'scenarios' }, skeletonList(4), h('div', { class: 'skeleton', style: { height: '420px' } })));
    try {
      items = await api('/scenarios');
    } catch (e) {
      if (alive) clear(body, errorState(e, load));
      return;
    }
    if (!alive) return;
    if (items.length === 0) {
      clear(body, stateView('empty', {
        title: '시드 시나리오 없음',
        desc: 'features/seeds/ 폴더에 .feature 파일을 추가하면 여기에 표시됩니다.',
        actions: [h('button', { class: 'btn', onclick: load }, '새로고침')],
      }));
      return;
    }
    if (!items.some((s) => s.id === memo.selected)) memo.selected = items[0].id;
    draw();
  }

  function draw() {
    const sc = items.find((s) => s.id === memo.selected);
    head.querySelector('.sub').textContent = `시드 ${items.length}개 · 시나리오를 골라 교란 탐색을 실행합니다`;
    clear(body, h('div', { class: 'scenarios' },
      h('div', { class: 'sc-list' }, items.map((it) => h('button', {
        class: `sc-item${it.id === memo.selected ? ' active' : ''}`,
        onclick: () => { memo.selected = it.id; draw(); },
      },
      h('div', { class: 'title' }, it.feature),
      h('div', { class: 'symptom' }, it.symptom || it.scenario),
      h('div', { class: 'row', style: { justifyContent: 'space-between' } },
        h('span', { class: 'id' }, it.id),
        h('span', { class: 'tags' }, it.tags.filter((t) => ORACLE_TAGS.has(t)).map((t) => h('span', { class: 'tag' }, t.replace('@oracle-', '')))),
      ),
      ))),
      detail(sc),
    ));
  }

  function selectedTags(sc) {
    if (!memo.tags[sc.id]) memo.tags[sc.id] = new Set(sc.tags.filter((t) => ORACLE_TAGS.has(t)));
    return memo.tags[sc.id];
  }

  function detail(sc) {
    const tags = selectedTags(sc);
    const health = ctx.health;
    const errorBox = h('div');

    const toggles = h('div', { class: 'toggles' },
      h('label', { class: 'toggle on locked', title: 'Then 스텝 실패 판정 (항상 활성)' },
        h('span', { class: 'box' }, '✓'), 'dom', h('span', { class: 'desc' }, 'Then 실패 · 항상')),
      ORACLES.map((o) => {
        const el = h('label', { class: `toggle${tags.has(o.tag) ? ' on' : ''}` },
          h('input', {
            type: 'checkbox', checked: tags.has(o.tag),
            onchange: (e) => {
              if (e.target.checked) tags.add(o.tag); else tags.delete(o.tag);
              el.classList.toggle('on', e.target.checked);
              el.querySelector('.box').textContent = e.target.checked ? '✓' : '';
            },
          }),
          h('span', { class: 'box' }, tags.has(o.tag) ? '✓' : ''), o.name, h('span', { class: 'desc' }, o.desc));
        return el;
      }),
    );

    const num = (key, label, min, max) => h('label', { class: 'field' }, label,
      h('input', {
        type: 'number', min, max, value: memo.options[key],
        onchange: (e) => {
          const v = Math.max(min, Math.min(max, Number(e.target.value) || DEFAULTS[key]));
          memo.options[key] = v;
          e.target.value = v;
        },
      }));
    const chk = (key, label) => h('label', { class: 'check' },
      h('input', { type: 'checkbox', checked: memo.options[key], onchange: (e) => { memo.options[key] = e.target.checked; } }), label);

    const active = health && health.active_run;
    const runBtn = h('button', { class: 'btn primary lg', disabled: !!active, onclick: () => start(sc, tags, runBtn, errorBox) }, '▶  탐색 실행');

    return h('div', { class: 'sc-detail' },
      h('div', { class: 'card card-body sc-title' },
        h('h2', {}, sc.feature),
        h('div', { class: 'symptom' }, sc.symptom ? `증상 : ${sc.symptom}` : '증상 설명 없음'),
        h('div', { class: 'row', style: { marginTop: '10px' } },
          h('span', { class: 'tag' }, sc.id), h('span', { class: 'tag' }, sc.file),
          h('span', { class: 'dim', style: { fontSize: '12px' } }, `${sc.scenario} · 스텝 ${sc.steps.length}개`)),
      ),
      health && !health.target_alive && h('div', { class: 'inline-alert warn' },
        h('span', {}, '⚠'),
        h('div', {}, '데모 서버가 응답하지 않아 실행이 실패합니다. ',
          h('code', {}, 'cd demo-shop && python -m demo_shop'), ` 로 ${health.base_url} 를 먼저 띄우세요.`)),
      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, '오라클', h('span', { class: 'right dim' }, '증상 판정 기준')),
        h('div', { class: 'card-body', style: { display: 'grid', gap: '16px' } },
          toggles,
          h('details', { class: 'adv' },
            h('summary', {}, '고급 옵션'),
            h('div', { style: { display: 'grid', gap: '12px' } },
              h('div', { class: 'options' },
                num('k', '후보별 반복 k', 1, 20), num('max_runs', '실행 예산 max_runs', 1, 1000),
                num('verify_n', '검증 반복 N', 1, 100), num('tries', '증거 run 시도', 1, 100)),
              h('div', { class: 'row', style: { gap: '20px' } },
                chk('headed', '브라우저 창 표시 (headed)'), chk('copy_generated', 'features/generated 에 복사')),
            )),
          h('div', { class: 'run-bar' },
            runBtn,
            active
              ? h('span', { class: 'dim' }, '다른 실행이 진행 중입니다 · ', h('a', { href: `#/run/${encodeURIComponent(active)}` }, '진행 화면 보기'))
              : h('span', { class: 'dim', style: { fontSize: '12px' } }, '탐색 → 최소화 → 검증 → 리포트 순서로 진행됩니다')),
          errorBox,
        ),
      ),
      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, 'feature 미리보기', h('span', { class: 'right mono' }, sc.file)),
        featureCode(sc.source),
      ),
    );
  }

  async function start(sc, tags, btn, errorBox) {
    btn.disabled = true;
    btn.textContent = '시작 중…';
    clear(errorBox);
    const keep = sc.tags.filter((t) => !ORACLE_TAGS.has(t));
    try {
      const res = await api('/runs', {
        method: 'POST',
        body: { scenario: sc.id, tags: [...keep, ...tags], ...memo.options },
      });
      ctx.lastRunId = res.id;
      toast(`실행 시작 · ${res.id}`);
      ctx.refreshHealth();
      ctx.navigate(`#/run/${encodeURIComponent(res.id)}`);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '▶  탐색 실행';
      const busy = e.status === 409;
      const hint = e.status === 503 ? ' — demo-shop 을 먼저 실행하세요 (cd demo-shop && python -m demo_shop)' : '';
      clear(errorBox, h('div', { class: 'inline-alert error' },
        h('span', {}, '✕'),
        h('div', {}, h('b', {}, busy ? '이미 실행 중' : '실행 시작 실패'), ` · ${e.message}${hint}`,
          busy && h('div', { style: { marginTop: '6px' } },
            h('a', { href: '#/run' }, '진행 중인 실행 보기 →')))));
      ctx.refreshHealth();
    }
  }

  // 실행 중 · 데모 서버 상태 변경 시 다시 그림
  const key = (hl) => (hl ? `${hl.active_run}|${hl.target_alive}` : '');
  let lastKey = key(ctx.health);
  const off = ctx.onHealth((hl) => {
    const k = key(hl);
    if (k !== lastKey && items.length) {
      lastKey = k;
      draw();
    }
  });

  load();
  return () => { alive = false; off(); };
}
