from retrace import steps  # noqa: F401
from retrace.minimizer import Minimizer, ddmin, normalize
from retrace.oracle import DomOracle
from retrace.scenario import parse_feature
from retrace.scenario.parser import Scenario, Step
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

ADD, APPLY, PAY = '"상품-1"을 장바구니에 담으면', '"10% 쿠폰"를 적용하면', '"결제" 버튼을 누르면'


def hit_seq():
    # 탐색 hit : 적용 뒤 뒤로가기 + 재적용 (7스텝)
    s = parse_feature(FEATURE).scenarios[0]
    pert = [Step("And", "브라우저 뒤로가기를 하면", perturbation="back"),
            Step("And", APPLY, perturbation="replay")]
    return Scenario(s.name, s.tags, [*s.steps[:3], *pert, *s.steps[3:]])


def result(sc, failed_at=None):
    rs = [
        StepResult(i, s.keyword, s.text, s.background,
                   "failed" if i == failed_at else "passed", error="x" if i == failed_at else None)
        for i, s in enumerate(sc.steps)
    ]
    return RunResult(sc.name, rs, failed_at)


def coupon_shop(calls):
    # BUG-02 모사 : 담기·결제 없거나 쿠폰 0회면 Then 실패(가짜 hit 유발), 2회 이상이면 이중 할인
    def run(sc):
        calls.append(sc)
        texts = [s.text for s in sc.steps]
        ok = ADD in texts and PAY in texts and texts.count(APPLY) == 1
        return result(sc, failed_at=None if ok else len(sc.steps) - 1)
    return run


def test_ddmin_finds_minimal_subset_without_retests():
    seen = []

    def test(sub):
        seen.append(tuple(sub))
        return {2, 5} <= set(sub)
    assert ddmin(list(range(8)), test) == [2, 5]
    assert len(seen) == len(set(seen))


def test_normalize_first_scenario_step_is_when():
    s = hit_seq().steps
    out = normalize([s[0], s[2], s[-1]])
    assert [x.keyword for x in out] == ["Given", "When", "Then"]


def test_bug02_drops_back_and_keeps_fixed_steps():
    calls = []
    res = Minimizer(coupon_shop(calls), [DomOracle()], k=3).minimize(hit_seq())
    assert res.stopped == "minimized"
    assert len(res.original) == 7 and len(res.minimized) == 6
    texts = [s.text for s in res.minimized]
    assert "브라우저 뒤로가기를 하면" not in texts
    assert texts.count(APPLY) == 2
    # Background·Then 유지
    assert res.minimized[0].background and res.minimized[-1].keyword == "Then"
    assert res.runs == len(calls)


def test_control_guard_rejects_removing_preconditions():
    res = Minimizer(coupon_shop([]), [DomOracle()], k=3).minimize(hit_seq())
    # 쿠폰·담기 제거 후보는 Then 실패해도 대조 실패로 기각
    rejected = [p for p in res.probes if p.outcome == "control_fail"]
    assert any(ADD not in p.steps or p.steps.count(APPLY) == 0 for p in rejected)
    # 채택된 후보는 전제 스텝 모두 보유
    for p in res.probes:
        if p.outcome == "hit":
            assert ADD in p.steps and PAY in p.steps and p.steps.count(APPLY) == 2


def test_invalid_runs_excluded_from_hit():
    # 교란 포함 run은 항상 When 실패(무효), 대조는 통과
    def run(sc):
        bad = next((i for i, s in enumerate(sc.steps) if s.perturbation), None)
        return result(sc, failed_at=bad)
    res = Minimizer(run, [DomOracle()], k=3).minimize(hit_seq())
    assert res.stopped == "not_reproduced"
    assert res.probes[0].outcome == "no_hit" and res.probes[0].runs == 1 + 3
    assert [s.text for s in res.minimized] == [s.text for s in hit_seq().steps]
