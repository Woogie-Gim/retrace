"""실행 관리 : 백그라운드 파이프라인(탐색 → 최소화 → 검증 → 리포트) + 이벤트 브로드캐스트"""
import asyncio
import json
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import steps  # noqa: F401  스텝 등록
from ..driver import SeleniumDriver
from ..explorer import Explorer, ExploreOptions, run_clean
from ..minimizer import Minimizer
from ..oracle import ApiOracle, ConsoleOracle, DomOracle, NetworkOracle, select_oracles
from ..reporter import build_report, load_repro
from ..scenario import save_result
from ..scenario.parser import Scenario
from ..verifier import verify


@dataclass
class RunOptions:
    tags: list[str] | None = None  # None이면 시드 태그 사용
    k: int = 3
    max_runs: int = 60
    prefer: list[str] = field(default_factory=list)
    verify_n: int = 10
    tries: int = 10
    headed: bool = False
    copy_generated: bool = False


@dataclass
class RunEnv:
    base_url: str
    seeds_dir: Path
    generated_dir: Path


class Run:
    def __init__(self, run_id: str, scenario_id: str, options: RunOptions, out_dir: Path,
                 loop: asyncio.AbstractEventLoop | None):
        self.id = run_id
        self.scenario_id = scenario_id
        self.options = options
        self.out_dir = out_dir
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.status = "running"  # running / ok / no_hit / not_reproduced / error
        self.result: dict | None = None
        self.events: list[dict] = []
        self._loop = loop
        self._subs: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    @property
    def finished(self) -> bool:
        return self.status != "running"

    def emit(self, event: str, data: dict | None = None) -> None:
        # 워커 스레드 → 구독자 큐 (이벤트 루프 스레드에서 put)
        with self._lock:
            ev = {"seq": len(self.events), "event": event, "ts": time.time(), "data": data or {}}
            self.events.append(ev)
            for q in self._subs:
                self._loop.call_soon_threadsafe(q.put_nowait, ev)

    def subscribe(self) -> tuple[list[dict], asyncio.Queue]:
        # backlog과 구독 등록을 원자적으로 → 누락·중복 없음
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subs.add(q)
            return list(self.events), q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def to_dict(self, events: bool = True) -> dict:
        out = {
            "id": self.id, "scenario": self.scenario_id, "status": self.status,
            "created_at": self.created_at, "options": asdict(self.options), "result": self.result,
        }
        if events:
            out["events"] = list(self.events)
        return out


def _verdicts(vs) -> list[dict]:
    return [asdict(v) for v in vs]


def _emitter(run: Run, max_runs: int) -> Callable[[str, dict], None]:
    # 엔진 on_event → JSON 직렬화 가능한 이벤트
    runs = 0

    def on_event(name: str, data: dict) -> None:
        nonlocal runs
        if name == "candidate_start":
            data = {"candidate": asdict(data["candidate"])}
        elif name == "run_done":
            runs += 1
            data = {**data, "verdicts": _verdicts(data["verdicts"]), "runs": runs, "max_runs": max_runs}
        elif name == "hit":
            h = data["hit"]  # RunResult 제외
            data = {"candidate": asdict(h.candidate), "hits": h.hits, "trials": h.trials,
                    "verdicts": _verdicts(h.verdicts)}
        elif name == "minimize_step":
            data = {"record": asdict(data["record"]), "size": data["size"]}
        run.emit(name, data)

    return on_event


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_pipeline(run: Run, scenario: Scenario, env: RunEnv) -> dict:
    """CLI explore → minimize → report 흐름, 결과는 run.out_dir에 저장"""
    o, out = run.options, run.out_dir
    out.mkdir(parents=True, exist_ok=True)
    tags = o.tags if o.tags is not None else scenario.tags
    sc = Scenario(scenario.name, tags, scenario.steps)
    on_event = _emitter(run, o.max_runs)

    with SeleniumDriver(headless=not o.headed) as driver:
        run_fn = lambda s: run_clean(driver, env.base_url, s)  # noqa: E731
        oracles = select_oracles(tags, driver, env.base_url)

        # 탐색
        opts = ExploreOptions(k=o.k, max_runs=o.max_runs, prefer=tuple(o.prefer))
        explorer = Explorer(driver, env.base_url, opts, oracles=oracles, on_event=on_event)
        run.emit("phase", {"phase": "explore", "candidates": len(explorer.candidates(sc)), "max_runs": o.max_runs})
        res = explorer.explore(sc)
        _write_json(out / "explore.json", res.to_dict())
        if not res.hits:
            return {"status": "no_hit", "stopped": res.stopped, "runs": res.runs}
        save_result(res.hits[0].result, out / "hit-00")

        # 최소화
        hit_sc = Scenario(sc.name, tags, res.hits[0].candidate.steps)
        run.emit("phase", {"phase": "minimize", "steps": len(hit_sc.steps)})
        mres = Minimizer(run_fn, oracles, k=o.k, on_event=on_event).minimize(hit_sc)
        report = {
            "source": str(out / "explore.json"), "tags": tags, "seed_count": len(scenario.steps),
            "minimize": mres.to_dict(), "verify": None,
        }
        if mres.stopped != "minimized":
            _write_json(out / "minimize.json", report)
            return {"status": "not_reproduced", "stopped": mres.stopped, "runs": res.runs + mres.runs}

        # 검증
        run.emit("phase", {"phase": "verify", "total": o.verify_n})
        ver = verify(Scenario(sc.name, tags, mres.minimized), run_fn, oracles, n=o.verify_n, on_event=on_event)
        report["verify"] = ver.to_dict()
        _write_json(out / "minimize.json", report)

        # 리포트 (같은 폴더에 report.json)
        run.emit("phase", {"phase": "report", "tries": o.tries})
        repro = load_repro(out / "minimize.json", env.seeds_dir)
        all_oracles = [DomOracle(), ConsoleOracle(), NetworkOracle(), ApiOracle(driver, env.base_url)]
        rep = build_report(
            repro, lambda s, d: run_clean(driver, env.base_url, s, out_dir=d),
            all_oracles, {x.kind for x in oracles}, out,
            generated_dir=env.generated_dir if o.copy_generated else None,
            driver_info=driver.info, tries=o.tries, on_event=on_event,
        )

    return {
        "status": "ok",
        "report_id": f"{run.id}/{repro.name}",
        "rate": rep["verify"]["rate"],
        "grade": rep["verify"]["grade"],
        "cause": rep["cause"]["layer"],
        "counts": rep["counts"],
    }


class BusyError(RuntimeError):
    pass


class RunManager:
    """동시 실행 1개 제한 (드라이버·demo-shop 상태 공유)"""

    def __init__(self, reports_dir: Path, env: RunEnv,
                 pipeline: Callable[[Run, Scenario, RunEnv], dict] = run_pipeline):
        self.reports_dir = Path(reports_dir)
        self.env = env
        self.pipeline = pipeline
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def active(self) -> Run | None:
        return next((r for r in self.runs.values() if not r.finished), None)

    def _new_id(self) -> str:
        base = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        rid, n = base, 1
        while rid in self.runs or (self.reports_dir / rid).exists():
            n += 1
            rid = f"{base}-{n}"
        return rid

    def start(self, scenario_id: str, scenario: Scenario, options: RunOptions,
              loop: asyncio.AbstractEventLoop) -> Run:
        with self._lock:
            if (cur := self.active()) is not None:
                raise BusyError(cur.id)
            rid = self._new_id()
            run = Run(rid, scenario_id, options, self.reports_dir / rid / scenario_id, loop)
            self.runs[rid] = run
        threading.Thread(target=self._work, args=(run, scenario), name=rid, daemon=True).start()
        return run

    def _work(self, run: Run, scenario: Scenario) -> None:
        run.emit("run_start", {"id": run.id, "scenario": run.scenario_id, "options": asdict(run.options)})
        try:
            result = self.pipeline(run, scenario, self.env)
        except Exception as e:  # noqa: BLE001  실패도 스트림으로 전달
            run.emit("error", {"message": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
            result = {"status": "error", "message": f"{type(e).__name__}: {e}"}
        run.result = result
        run.status = result.get("status", "ok")
        run.emit("done", result)
