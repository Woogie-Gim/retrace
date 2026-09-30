from retrace import steps  # noqa: F401
from retrace.explorer import Explorer, ExploreOptions, judge
from retrace.oracle import DomOracle
from retrace.scenario import parse_feature
from retrace.scenario.runner import RunResult, StepResult

FEATURE = """
Feature: 시드
  Background:
    Given "골드" 등급 회원으로 로그인하면

  Scenario: 쿠폰 결제
    When "상품-1"을 장바구니에 담으면
    And "10% 쿠폰"를 적용하면
    And "결제" 버튼을 누르면
    Then 결제 금액은 "27000"원이다
"""


def seed():
    return parse_feature(FEATURE).scenarios[0]


def result(sc, failed_at=None):
    rs = [
        StepResult(i, s.keyword, s.text, s.background,
                   "failed" if i == failed_at else "passed", error="x" if i == failed_at else None)
        for i, s in enumerate(sc.steps)
    ]
    return RunResult(sc.name, rs, failed_at)


def test_positions_exclude_background_and_then():
    cands = Explorer(None, "x").candidates(seed())
    # 로그인(0) 뒤 ~ 결제 클릭(3) 뒤, Then(4) 뒤 없음
    assert {c.position for c in cands} == {0, 1, 2, 3}
    for c in cands:
        assert not any(s.perturbation for s in c.steps[: c.position + 1])
        assert c.steps[-1].keyword == "Then"


def test_priority_and_kind_order():
    cands = Explorer(None, "x").candidates(seed())
    first = cands[0]
    assert first.kind == "rapid_click" and first.position == 3
    assert first.label == '"결제" 버튼을 빠르게 3회 누르면'
    # 상태 변경 스텝 뒤 후보가 먼저
    prio = [c.priority for c in cands]
    assert prio == sorted(prio, reverse=True)
    assert not cands[-1].priority and cands[-1].position == 0


def test_prefer_kind_goes_first():
    cands = Explorer(None, "x", ExploreOptions(prefer=("network",))).candidates(seed())
    kinds = [c.kind for c in cands]
    n = kinds.count("network")
    assert n and kinds[:n] == ["network"] * n
    # 우선 종류 내에서도 상태 변경 직후 우선
    assert cands[0].priority
    # 나머지는 기존 순서 유지
    base = [(c.kind, c.position) for c in Explorer(None, "x").candidates(seed()) if c.kind != "network"]
    assert [(c.kind, c.position) for c in cands[n:]] == base


def test_back_replays_idempotent_step():
    cands = Explorer(None, "x").candidates(seed())
    back = {c.position: c for c in cands if c.kind == "back"}
    assert [s.text for s in back[2].inserted] == ["브라우저 뒤로가기를 하면", '"10% 쿠폰"를 적용하면']
    # 담기는 멱등 아님 → 재실행 없음
    assert len(back[1].inserted) == 1
    # 시나리오 첫 위치 삽입은 When
    assert back[0].inserted[0].keyword == "When"


def test_judge_then_failure_is_hit_and_when_failure_is_invalid():
    sc = seed()
    assert judge(result(sc, failed_at=4), [DomOracle()])[0] == "hit"
    assert judge(result(sc, failed_at=2), [DomOracle()])[0] == "invalid"
    assert judge(result(sc), [DomOracle()])[0] == "pass"


def make_runner(hit_when):
    calls = []

    def run(sc):
        calls.append(sc)
        return result(sc, failed_at=len(sc.steps) - 1 if hit_when(sc, len(calls)) else None)

    return run, calls


def test_first_hit_stops_early():
    # 뒤로가기+재적용 후보에서 2번째 시도에 적중
    replay_runs = []

    def hit_when(sc, n):
        if any(s.perturbation == "replay" for s in sc.steps):
            replay_runs.append(n)
            return len(replay_runs) == 2
        return False
    run, calls = make_runner(hit_when)
    res = Explorer(None, "x", run_fn=run, oracles=[DomOracle()]).explore(seed())
    assert res.stopped == "first_hit"
    h = res.hits[0]
    assert h.candidate.kind == "back" and h.trials == 2 and h.hits == 1
    # baseline 1 + 앞선 후보 2개×3 + 2
    assert res.runs == 1 + 2 * 3 + 2 == len(calls)


def test_budget_limits_runs():
    run, calls = make_runner(lambda sc, n: False)
    res = Explorer(None, "x", ExploreOptions(max_runs=10), run_fn=run, oracles=[DomOracle()]).explore(seed())
    assert res.stopped == "budget" and res.runs == 10 and not res.hits


def test_baseline_hit_aborts():
    run, calls = make_runner(lambda sc, n: True)
    res = Explorer(None, "x", run_fn=run, oracles=[DomOracle()]).explore(seed())
    assert res.stopped == "baseline_hit" and res.runs == 1


def test_collect_all_ranks_by_rate():
    # 연타 후보 3/3, 뒤로가기(위치 1) 1/3
    def hit_when(sc, n):
        kinds = [s.perturbation for s in sc.steps if s.perturbation]
        if kinds == ["rapid_click"]:
            return True
        return kinds == ["back"] and n % 3 == 0
    run, _ = make_runner(hit_when)
    opts = ExploreOptions(collect_all=True, top_n=2, max_runs=200)
    res = Explorer(None, "x", opts, run_fn=run, oracles=[DomOracle()]).explore(seed())
    assert res.stopped == "exhausted"
    assert res.hits[0].candidate.kind == "rapid_click" and res.hits[0].hits == 3
    assert len(res.hits) == 2
