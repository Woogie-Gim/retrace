from retrace.oracle import ConsoleOracle, DomOracle, NetworkOracle, failed_keyword, select_oracles
from retrace.scenario.runner import RunResult, StepResult


def run(keywords, failed_at=None, console=(), network=()):
    steps = [
        StepResult(i, k, f"s{i}", False, "failed" if i == failed_at else "passed",
                   error="AssertionError: 불일치" if i == failed_at else None)
        for i, k in enumerate(keywords)
    ]
    return RunResult("t", steps, failed_at, logs={"console": list(console), "network": list(network)})


def test_failed_keyword_inherits_and():
    kws = ["Given", "When", "And", "Then", "And"]
    assert failed_keyword(run(kws)) is None
    assert failed_keyword(run(kws, 2)) == "When"
    assert failed_keyword(run(kws, 4)) == "Then"


def test_dom_oracle():
    assert not DomOracle().check(run(["Given", "Then"])).hit
    v = DomOracle().check(run(["Given", "Then"], 1))
    assert v.hit and v.kind == "dom" and "불일치" in v.detail


def test_console_oracle_severe_only():
    logs = [{"level": "WARNING", "message": "w"}, {"level": "INFO", "message": "i"}]
    assert not ConsoleOracle().check(run(["Then"], console=logs)).hit
    logs.append({"level": "SEVERE", "message": "Uncaught TypeError"})
    v = ConsoleOracle().check(run(["Then"], console=logs))
    assert v.hit and "TypeError" in v.detail


def test_network_oracle_4xx_5xx():
    ok = [
        {"event": "requestWillBeSent", "status": None, "url": "/a"},
        {"event": "responseReceived", "status": 200, "url": "/a"},
        {"event": "loadingFailed", "status": None, "url": "/b"},
    ]
    assert not NetworkOracle().check(run(["Then"], network=ok)).hit
    bad = ok + [{"event": "responseReceived", "status": 409, "url": "/api/cart"}]
    v = NetworkOracle().check(run(["Then"], network=bad))
    assert v.hit and "409" in v.detail


def test_select_oracles_by_tag():
    kinds = lambda tags: [o.kind for o in select_oracles(tags, None, "x")]
    assert kinds([]) == ["dom"]
    assert kinds(["@oracle-api", "@oracle-console"]) == ["dom", "console", "api"]
    assert kinds(["@oracle-network"]) == ["dom", "network"]
