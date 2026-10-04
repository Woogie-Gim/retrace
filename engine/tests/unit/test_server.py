import json
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from retrace import config
from retrace.server import app as server_app
from retrace.server.app import create_app
from retrace.server.runs import RunEnv, RunManager

SEEDS = config.ROOT_DIR / "features" / "seeds"


def fake_pipeline(gate: threading.Event | None = None):
    # 실제 브라우저 없이 이벤트만 발행
    def pipeline(run, scenario, env):
        run.emit("phase", {"phase": "explore", "candidates": 2, "max_runs": run.options.max_runs})
        run.emit("candidate_start", {"candidate": {"index": 0}})
        if gate is not None:
            gate.wait(5)
        run.emit("hit", {"hits": 1, "trials": 1})
        run.emit("verify_progress", {"trial": 0, "total": 1, "status": "hit"})
        return {"status": "ok", "report_id": f"{run.id}/{run.scenario_id}"}
    return pipeline


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "target_alive", lambda base: True)

    def make(pipeline=None):
        env = RunEnv("http://shop", SEEDS, tmp_path / "generated")
        manager = RunManager(tmp_path, env, pipeline or fake_pipeline())
        return TestClient(create_app(reports_dir=tmp_path, seeds_dir=SEEDS, manager=manager, base_url="http://shop"))
    return make


def write_report(root, run, name, created_at):
    d = root / run / name
    d.mkdir(parents=True)
    (d / "report.json").write_text(json.dumps({
        "name": name, "feature": "F", "symptom": "s", "created_at": created_at,
        "verify": {"rate": 1.0, "grade": "확정"}, "cause": {"layer": "BE"}, "counts": {"seed": 4},
    }), encoding="utf-8")
    (d / "evidence").mkdir()
    (d / "evidence" / "console.json").write_text("[]", encoding="utf-8")


def test_health(make_client):
    r = make_client().get("/health").json()
    assert r["status"] == "ok" and r["target_alive"] is True and r["active_run"] is None


def test_scenarios(make_client):
    items = make_client().get("/scenarios").json()
    ids = {s["id"] for s in items}
    assert {"gold_coupon-00", "double_order-00", "cart_qty-00", "empty_products-00"} <= ids
    gold = next(s for s in items if s["id"] == "gold_coupon-00")
    assert "@oracle-api" in gold["tags"] and gold["steps"][0]["background"]
    assert gold["source"].startswith("@oracle-api")


def test_reports(make_client, tmp_path):
    write_report(tmp_path, "report-1", "a-00", "2026-09-30T10:00:00")
    write_report(tmp_path, "report-2", "b-00", "2026-09-30T11:00:00")
    c = make_client()
    items = c.get("/reports").json()
    assert [r["id"] for r in items] == ["report-2/b-00", "report-1/a-00"]
    assert items[0]["cause"] == "BE" and items[0]["verify"]["grade"] == "확정"
    detail = c.get("/reports/report-1/a-00").json()
    assert detail["id"] == "report-1/a-00" and detail["name"] == "a-00"
    assert c.get("/files/report-1/a-00/evidence/console.json").json() == []
    assert c.get("/reports/report-1/none").status_code == 404
    assert c.get("/reports/../secret").status_code == 404


def test_run_unknown_scenario(make_client):
    assert make_client().post("/runs", json={"scenario": "nope-00"}).status_code == 404


def test_run_target_down(make_client, monkeypatch):
    c = make_client()
    monkeypatch.setattr(server_app, "target_alive", lambda base: False)
    assert c.post("/runs", json={"scenario": "gold_coupon-00"}).status_code == 503


def test_run_stream(make_client):
    gate = threading.Event()
    with make_client(fake_pipeline(gate)) as c:
        r = c.post("/runs", json={"scenario": "gold_coupon-00", "max_runs": 5})
        assert r.status_code == 202
        run_id = r.json()["id"]
        # 실행 중 중복 요청 거부
        assert c.post("/runs", json={"scenario": "gold_coupon-00"}).status_code == 409
        with c.websocket_connect(f"/runs/{run_id}/stream") as ws:
            first = ws.receive_json()
            assert first["event"] == "run_start"
            gate.set()
            events = [first]
            while events[-1]["event"] != "done":
                events.append(ws.receive_json())
        names = [e["event"] for e in events]
        assert names == ["run_start", "phase", "candidate_start", "hit", "verify_progress", "done"]
        assert [e["seq"] for e in events] == list(range(len(events)))
        assert events[-1]["data"]["report_id"] == f"{run_id}/gold_coupon-00"

        run = c.get(f"/runs/{run_id}").json()
        assert run["status"] == "ok" and len(run["events"]) == 6
        # 종료 후 재연결 시 backlog 재생
        with c.websocket_connect(f"/runs/{run_id}/stream") as ws:
            replay = [ws.receive_json() for _ in range(6)]
        assert [e["event"] for e in replay] == names


def test_run_error(make_client):
    def boom(run, scenario, env):
        raise RuntimeError("driver failed")
    with make_client(boom) as c:
        run_id = c.post("/runs", json={"scenario": "gold_coupon-00"}).json()["id"]
        with c.websocket_connect(f"/runs/{run_id}/stream") as ws:
            events = [ws.receive_json()]
            while events[-1]["event"] != "done":
                events.append(ws.receive_json())
        assert [e["event"] for e in events] == ["run_start", "error", "done"]
        assert events[-1]["data"]["status"] == "error"
        assert "driver failed" in events[1]["data"]["message"]


def test_stream_unknown_run(make_client):
    with make_client().websocket_connect("/runs/nope/stream") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4404
