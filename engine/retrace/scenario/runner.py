"""실행기 : 시나리오 스텝 순차 실행 → RunResult"""
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from ..driver import Driver
from .parser import Scenario
from .registry import StepContext, StepRegistry, registry as default_registry


@dataclass
class StepResult:
    index: int
    keyword: str
    text: str
    background: bool
    status: str               # passed / failed / skipped
    error: str | None = None
    duration_ms: int = 0
    screenshot: str | None = None


@dataclass
class RunResult:
    scenario: str
    steps: list[StepResult]
    failed_at: int | None
    logs: dict[str, list[dict]] = field(default_factory=lambda: {"console": [], "network": []})
    screenshots: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def passed(self) -> bool:
        return self.failed_at is None

    def to_dict(self) -> dict:
        return {**asdict(self), "passed": self.passed}


def reset_target(base_url: str) -> None:
    # 드라이버 재사용, 타깃 상태만 초기화
    requests.post(base_url.rstrip("/") + "/api/reset", timeout=5).raise_for_status()


def run_scenario(
    scenario: Scenario,
    driver: Driver,
    base_url: str,
    out_dir: str | Path | None = None,
    registry: StepRegistry | None = None,
) -> RunResult:
    registry = registry or default_registry
    reset_target(base_url)
    # 이전 실행 로그 버퍼 비우기
    driver.console_logs()
    driver.network_logs()

    ctx = StepContext(driver=driver, base_url=base_url)
    shot_dir = Path(out_dir) / "screenshots" if out_dir else None
    results: list[StepResult] = []
    failed_at = None
    started = time.perf_counter()

    for i, s in enumerate(scenario.steps):
        r = StepResult(i, s.keyword, s.text, s.background, "skipped")
        results.append(r)
        if failed_at is not None:
            continue
        t = time.perf_counter()
        try:
            registry.run(ctx, s.text)
            r.status = "passed"
        except Exception as e:
            r.status = "failed"
            r.error = f"{type(e).__name__}: {e}".strip()
            r.error += "\n" + traceback.format_exc(limit=3)
            failed_at = i
        r.duration_ms = int((time.perf_counter() - t) * 1000)
        if shot_dir:
            path = shot_dir / f"{i:02d}.png"
            try:
                driver.screenshot(str(path))
                r.screenshot = str(path)
            except Exception:
                pass

    return RunResult(
        scenario=scenario.name,
        steps=results,
        failed_at=failed_at,
        logs={"console": driver.console_logs(), "network": driver.network_logs()},
        screenshots=[r.screenshot for r in results if r.screenshot],
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_result(result: RunResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _dump(out / "result.json", result.to_dict())
    _dump(out / "console.json", result.logs["console"])
    _dump(out / "network.json", result.logs["network"])
    return out
