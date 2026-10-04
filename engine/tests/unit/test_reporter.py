import json

from retrace import steps  # noqa: F401  스텝 등록
from retrace.oracle import DomOracle, Verdict
from retrace.reporter import build_report, classify, format_feature, load_repro, pick_latest, render_md
from retrace.scenario import parse_feature, registry
from retrace.scenario.parser import Step
from retrace.scenario.runner import RunResult, StepResult

REQ = {"event": "requestWillBeSent", "request_id": "1", "url": "http://x/api/products"}


def logs(network=(), console=()):
    return {"network": list(network), "console": list(console)}


def dom(hit=True):
    return Verdict(hit, "dom", "Then 확인 → AssertionError: x")


def api(hit, detail="주문 일치: 주문 화면 1건 / API 1건"):
    return Verdict(hit, "api", detail)


# 원인 계층 분류
def test_5xx_is_be():
    res = {"event": "responseReceived", "request_id": "1", "url": "http://x/api/orders", "status": 500}
    assert classify([dom(), api(True)], logs([res])).layer == "BE"


def test_api_mismatch_is_fe():
    assert classify([dom(), api(True, "장바구니 수량 불일치")], logs()).layer == "FE"


def test_api_consistent_but_wrong_is_be():
    c = classify([dom(), api(False)], logs())
    assert c.layer == "BE" and "API 값 이상" in c.reason


def test_api_uncomparable_not_be():
    assert classify([dom(), api(False, "비교 불가: TimeoutException")], logs()).layer == "미분류"


def test_client_abort_is_fe():
    fail = {"event": "loadingFailed", "request_id": "1", "url": None, "error": "net::ERR_ABORTED"}
    c = classify([dom()], logs([REQ, fail]))
    assert c.layer == "FE" and "/api/products" in c.reason


def test_console_only_is_fe():
    assert classify([dom(False)], logs(console=[{"level": "SEVERE", "message": "TypeError"}])).layer == "FE"


def test_unknown():
    assert classify([dom()], logs()).layer == "미분류"


# feature 출력
STEPS = [
    Step("Given", '"일반" 등급 회원으로 로그인하면', background=True),
    Step("When", '네트워크를 "slow-3g" 상태로 바꾸면', perturbation="network"),
    Step("When", '"상품 목록" 화면을 열면'),
    Step("Then", '상품 목록에 "상품-1"이 보인다'),
]


def test_format_feature_roundtrip():
    text = format_feature("상품 목록 빈 화면", "상품 목록 확인 (최소 재현)", STEPS,
                          tags=["@oracle-console"], description=["증상: 빈 화면"], header=["생성"])
    assert "    And \"상품 목록\" 화면을 열면" in text and "# 교란(network)" in text
    sc = parse_feature(text).scenarios[0]
    assert [s.text for s in sc.steps] == [s.text for s in STEPS]
    assert [s.background for s in sc.steps] == [True, False, False, False]
    assert sc.tags == ["@oracle-console"]
    for s in sc.steps:
        registry.match(s.text)


# 입력 선택
def _minimize(root, run, name, stopped="minimized", tags=True):
    d = root / run / name
    d.mkdir(parents=True)
    data = {
        "source": "x", "seed_count": 3,
        "minimize": {"scenario": "상품 목록 확인", "stopped": stopped, "original": [], "original_count": 4,
                     "minimized": [{"keyword": s.keyword, "text": s.text, "line": 0, "background": s.background,
                                    "perturbation": s.perturbation} for s in STEPS]},
        "verify": {"runs": 10, "hits": 10, "passes": 0, "invalid": 0, "rate": 1.0, "grade": "확정",
                   "fixed": None, "attempts": []},
    }
    if tags:
        data["tags"] = ["@oracle-console"]
    (d / "minimize.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d / "minimize.json"


def test_pick_latest(tmp_path):
    a = _minimize(tmp_path, "minimize-20260101-000000", "empty_products-00")
    _minimize(tmp_path, "minimize-20260102-000000", "empty_products-00", stopped="not_reproduced")
    b = _minimize(tmp_path, "minimize-20260101-000000", "cart_qty-00")
    c = _minimize(tmp_path, "minimize-20260103-000000", "cart_qty-00")
    assert pick_latest([c, b, a, tmp_path / "minimize-20260102-000000/empty_products-00/minimize.json"]) == [c, a]


# 리포트 생성
def _seeds(tmp_path):
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "empty_products.feature").write_text(
        "@oracle-console @oracle-network\nFeature: 상품 목록 빈 화면\n  증상: 가끔 빈 화면\n\n"
        "  Background:\n    Given \"일반\" 등급 회원으로 로그인하면\n\n"
        "  Scenario: 상품 목록 확인\n    When \"상품 목록\" 화면을 열면\n    Then 상품 목록에 \"상품-1\"이 보인다\n",
        encoding="utf-8",
    )
    return seeds


def runner(pattern, net=()):
    # pattern : h(Then 실패) / p(통과) 순환
    n = 0

    def run(sc, out):
        nonlocal n
        c = pattern[n % len(pattern)]
        n += 1
        failed_at = len(sc.steps) - 1 if c == "h" else None
        rs = []
        for i, s in enumerate(sc.steps):
            shot = out / "screenshots" / f"{i:02d}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            shot.write_bytes(b"")
            rs.append(StepResult(i, s.keyword, s.text, s.background,
                                 "failed" if i == failed_at else "passed",
                                 error="AssertionError: 상품 목록에 상품-1 없음" if i == failed_at else None,
                                 screenshot=str(shot)))
        return RunResult(sc.name, rs, failed_at, logs={"console": [], "network": list(net)})
    return run


def test_build_report(tmp_path):
    repro = load_repro(_minimize(tmp_path, "minimize-1", "empty_products-00", tags=False), _seeds(tmp_path))
    assert repro.tags == ["@oracle-console", "@oracle-network"] and repro.symptom == "가끔 빈 화면"
    fail = {"event": "loadingFailed", "request_id": "1", "error": "net::ERR_ABORTED"}
    out, gen = tmp_path / "out", tmp_path / "generated"
    events = []
    rep = build_report(repro, runner("ph", [REQ, fail]), [DomOracle()], {"dom"}, out, gen,
                       driver_info=lambda: {"browser": "chrome 1", "window": "1280x800"},
                       on_event=lambda name, data: events.append(data["status"]))
    assert events == ["pass", "hit"]
    assert rep["evidence"]["status"] == "hit" and rep["evidence"]["tries"] == 2
    assert rep["cause"]["layer"] == "FE"
    assert rep["actual"] == "상품 목록에 상품-1 없음"
    assert rep["expected"] == '상품 목록에 "상품-1"이 보인다'
    assert rep["environment"] == {"browser": "chrome 1", "window": "1280x800", "network": "slow-3g"}
    assert rep["evidence"]["screenshots"][0]["path"] == "evidence/screenshots/00.png"
    for f in ("repro.feature", "report.md", "report.json", "evidence/console.json", "evidence/network.json"):
        assert (out / f).exists(), f
    assert (gen / "empty_products-00.feature").read_text(encoding="utf-8") == \
        (out / "repro.feature").read_text(encoding="utf-8")
    md = (out / "report.md").read_text(encoding="utf-8")
    assert md.startswith("## [확정 100%] 상품 목록 빈 화면")
    for section in ("### 재현 스텝", "### 기대 결과", "### 실제 결과", "### 증거", "← 탐색으로 찾은 교란"):
        assert section in md


def test_build_report_no_hit(tmp_path):
    repro = load_repro(_minimize(tmp_path, "minimize-1", "empty_products-00"), _seeds(tmp_path))
    rep = build_report(repro, runner("p"), [DomOracle()], {"dom"}, tmp_path / "out", tries=3)
    assert rep["evidence"] == {**rep["evidence"], "status": "pass", "tries": 3}
    assert rep["cause"]["layer"] == "미분류" and rep["generated"] is None
    assert "미적중" in render_md(rep)
