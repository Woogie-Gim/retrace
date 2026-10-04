"""엔진 서버 : 시드·실행·리포트 API + 실행 진행 WebSocket 스트림"""
import asyncio
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, config
from . import store
from .runs import BusyError, RunEnv, RunManager, RunOptions


class RunRequest(BaseModel):
    scenario: str = Field(description="시나리오 id (<시드 stem>-NN)")
    tags: list[str] | None = Field(None, description="오라클 태그 덮어쓰기, 생략 시 시드 태그")
    k: int = Field(3, ge=1, le=20)
    max_runs: int = Field(60, ge=1, le=1000)
    prefer: list[str] = []
    verify_n: int = Field(10, ge=1, le=100)
    tries: int = Field(10, ge=1, le=100)
    headed: bool = False
    copy_generated: bool = False


def target_alive(base_url: str) -> bool:
    try:
        return requests.get(base_url + "/api/config", timeout=1).ok
    except requests.RequestException:
        return False


def create_app(
    reports_dir: Path | None = None,
    seeds_dir: Path | None = None,
    manager: RunManager | None = None,
    base_url: str | None = None,
) -> FastAPI:
    reports_dir = Path(reports_dir or config.REPORTS_DIR)
    seeds_dir = Path(seeds_dir or config.ROOT_DIR / "features" / "seeds")
    base_url = base_url or config.BASE_URL
    env = RunEnv(base_url, seeds_dir, config.ROOT_DIR / "features" / "generated")
    manager = manager or RunManager(reports_dir, env)
    reports_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Retrace Engine", version=__version__)
    app.state.manager = manager
    # Electron 렌더러 (file:// · 개발 서버) 접근 허용
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        active = manager.active()
        return {
            "status": "ok",
            "version": __version__,
            "base_url": base_url,
            "target_alive": target_alive(base_url),
            "active_run": active.id if active else None,
        }

    @app.get("/scenarios")
    def scenarios():
        return store.list_scenarios(seeds_dir)

    @app.post("/runs", status_code=202)
    async def start_run(req: RunRequest):
        sc = await run_in_threadpool(store.find_scenario, seeds_dir, req.scenario)
        if sc is None:
            raise HTTPException(404, f"시나리오 없음: {req.scenario}")
        if not await run_in_threadpool(target_alive, base_url):
            raise HTTPException(503, f"데모 서버 미기동: {base_url}")
        opts = RunOptions(**req.model_dump(exclude={"scenario"}))
        try:
            run = manager.start(req.scenario, sc, opts, asyncio.get_running_loop())
        except BusyError as e:
            raise HTTPException(409, f"실행 중: {e}") from None
        return {"id": run.id, "status": run.status, "stream": f"/runs/{run.id}/stream"}

    @app.get("/runs")
    def list_runs():
        return [r.to_dict(events=False) for r in reversed(manager.runs.values())]

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        run = manager.get(run_id)
        if run is None:
            raise HTTPException(404, f"실행 없음: {run_id}")
        return run.to_dict()

    @app.websocket("/runs/{run_id}/stream")
    async def stream(ws: WebSocket, run_id: str):
        await ws.accept()
        run = manager.get(run_id)
        if run is None:
            await ws.close(code=4404, reason="run not found")
            return
        # 쌓인 이벤트 먼저 → 실시간, done 후 종료
        backlog, q = run.subscribe()
        try:
            for ev in backlog:
                await ws.send_json(ev)
                if ev["event"] == "done":
                    break
            else:
                while True:
                    ev = await q.get()
                    await ws.send_json(ev)
                    if ev["event"] == "done":
                        break
            await ws.close()
        except WebSocketDisconnect:
            pass
        finally:
            run.unsubscribe(q)

    @app.get("/reports")
    def reports():
        return store.list_reports(reports_dir)

    @app.get("/reports/{report_id:path}")
    def report(report_id: str):
        data = store.load_report(reports_dir, report_id)
        if data is None:
            raise HTTPException(404, f"리포트 없음: {report_id}")
        return data

    # 스크린샷·로그 파일 (report.json 상대 경로 → /files/<리포트 id>/<경로>)
    app.mount("/files", StaticFiles(directory=reports_dir), name="files")
    return app
