from retrace.oracle import DomOracle
from retrace.scenario.parser import Scenario, Step
from retrace.scenario.runner import RunResult, StepResult
from retrace.verifier import grade, verify

SC = Scenario("s", [], [Step("Given", "로그인", background=True), Step("When", "결제"), Step("Then", "확인")])


def runner(pattern):
    # pattern : h(hit) / p(pass) / i(invalid) 순환
    n = 0

    def run(sc):
        nonlocal n
        c = pattern[n % len(pattern)]
        n += 1
        failed_at = {"h": 2, "i": 1, "p": None}[c]
        rs = [StepResult(i, s.keyword, s.text, s.background,
                         "failed" if i == failed_at else "passed", error="x" if i == failed_at else None)
              for i, s in enumerate(sc.steps)]
        return RunResult(sc.name, rs, failed_at)
    return run


def test_grade_boundaries():
    assert grade(10, 10) == "확정"
    assert grade(3, 10) == "간헐"
    assert grade(29, 100) == "희귀"
    assert grade(0, 10) == "미재현"
    assert grade(0, 0) == "판정불가"


def test_invalid_excluded_from_rate():
    res = verify(SC, runner("hpi"), [DomOracle()], n=9)
    assert (res.hits, res.passes, res.invalid) == (3, 3, 3)
    assert res.rate == 0.5 and res.grade == "간헐"
    assert res.fixed is None and len(res.attempts) == 9
    assert res.to_dict()["grade"] == "간헐"


def test_all_invalid_is_unknown():
    res = verify(SC, runner("i"), [DomOracle()], n=5)
    assert res.rate is None and res.grade == "판정불가"


def test_expect_fixed():
    assert verify(SC, runner("p"), [DomOracle()], n=5, expect_fixed=True).fixed is True
    assert verify(SC, runner("ppppph"), [DomOracle()], n=6, expect_fixed=True).fixed is False
    assert verify(SC, runner("i"), [DomOracle()], n=3, expect_fixed=True).fixed is False
