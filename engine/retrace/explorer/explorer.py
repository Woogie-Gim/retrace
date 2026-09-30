"""탐색기 : 시드 시나리오에 교란 삽입 → 반복 실행 → 오라클 판정"""
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Callable

from ..driver import Driver
from ..oracle import Oracle, Verdict, failed_keyword, select_oracles
from ..oracle.dom import effective_keywords
from ..scenario.parser import Scenario, Step
from ..scenario.registry import StepRegistry, registry as default_registry
from ..scenario.runner import RunResult, run_scenario
from .catalog import KINDS, CatalogOptions, perturbations

# 직전 스텝 문장에 포함되면 우선 삽입 (상태 변경 스텝)
STATE_KEYWORDS = ("결제", "적용", "담")


@dataclass
class ExploreOptions:
    k: int = 3                 # 후보당 반복 횟수
    max_runs: int = 60         # 전체 실행 예산 (baseline 포함)
    collect_all: bool = False  # True면 예산 소진까지 hit 수집
    top_n: int = 5
    window: tuple[int, int] = (1280, 800)  # run마다 복구할 창 크기
    state_keywords: tuple[str, ...] = STATE_KEYWORDS
    prefer: tuple[str, ...] = ()  # 맨 앞에 둘 교란 종류
    catalog: CatalogOptions = field(default_factory=CatalogOptions)


@dataclass
class Candidate:
    index: int
    position: int       # 이 스텝 인덱스 뒤에 삽입 (-1 = 맨 앞)
    kind: str
    priority: bool
    steps: list[Step]   # 교란 포함 전체 시퀀스

    @property
    def inserted(self) -> list[Step]:
        return [s for s in self.steps if s.perturbation]

    @property
    def label(self) -> str:
        return " + ".join(s.text for s in self.inserted)


@dataclass
class Attempt:
    candidate: int      # -1 = baseline
    trial: int
    status: str         # hit / pass / invalid
    verdicts: list[Verdict]
    duration_ms: int


@dataclass
class Hit:
    candidate: Candidate
    hits: int           # 실행 횟수 중 적중 횟수
    trials: int
    verdicts: list[Verdict]
    result: RunResult


@dataclass
class ExploreResult:
    scenario: str
    candidates: int
    runs: int
    hits: list[Hit]
    attempts: list[Attempt]
    stopped: str        # first_hit / exhausted / budget / baseline_hit / baseline_invalid

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "candidates": self.candidates,
            "runs": self.runs,
            "stopped": self.stopped,
            "hits": [
                {
                    "candidate": asdict(h.candidate),
                    "hits": h.hits,
                    "trials": h.trials,
                    "verdicts": [asdict(v) for v in h.verdicts],
                }
                for h in self.hits
            ],
            "attempts": [asdict(a) for a in self.attempts],
        }


def judge(result: RunResult, oracles: list[Oracle]) -> tuple[str, list[Verdict]]:
    # Given/When 실패 = 교란으로 흐름 붕괴 → 무효 (오라클 생략)
    kw = failed_keyword(result)
    if kw is not None and kw != "Then":
        s = result.steps[result.failed_at]
        return "invalid", [Verdict(False, "dom", f"무효 run: {s.keyword} {s.text} 실패")]
    verdicts = [v for o in oracles if (v := o.check(result)) is not None]
    return ("hit" if any(v.hit for v in verdicts) else "pass"), verdicts


def run_clean(
    driver: Driver,
    base_url: str,
    scenario: Scenario,
    window: tuple[int, int] = (1280, 800),
    registry: StepRegistry | None = None,
) -> RunResult:
    # 이전 run 교란 원상 복구 후 실행
    driver.set_network("fast")
    driver.resize(*window)
    return run_scenario(scenario, driver, base_url, registry=registry)


class Explorer:
    def __init__(
        self,
        driver: Driver | None,
        base_url: str,
        options: ExploreOptions | None = None,
        registry: StepRegistry | None = None,
        oracles: list[Oracle] | None = None,
        run_fn: Callable[[Scenario], RunResult] | None = None,
        on_event: Callable[[str, dict], None] | None = None,
    ):
        self.driver = driver
        self.base_url = base_url
        self.opts = options or ExploreOptions()
        self.registry = registry or default_registry
        self.oracles = oracles
        self.run_fn = run_fn or self._run
        self.on_event = on_event or (lambda name, data: None)

    def _run(self, scenario: Scenario) -> RunResult:
        return run_clean(self.driver, self.base_url, scenario, self.opts.window, self.registry)

    # 후보 생성
    def candidates(self, scenario: Scenario) -> list[Candidate]:
        steps = scenario.steps
        eff = effective_keywords([s.keyword for s in steps])
        bg_end = sum(1 for s in steps if s.background)
        first_then = next((i for i in range(bg_end, len(steps)) if eff[i] == "Then"), len(steps))

        out: list[Candidate] = []
        # 삽입 위치 : 마지막 Background 스텝 뒤 ~ 첫 Then 앞
        for pos in range(bg_end - 1, first_then):
            prev = steps[pos] if pos >= 0 else None
            priority = prev is not None and not prev.background and any(
                w in prev.text for w in self.opts.state_keywords
            )
            for kind, inserted in perturbations(prev, self.registry, self.opts.catalog):
                if pos == bg_end - 1:
                    # 시나리오 첫 스텝 위치는 When으로 시작
                    inserted = [replace(inserted[0], keyword="When"), *inserted[1:]]
                seq = [*steps[: pos + 1], *inserted, *steps[pos + 1:]]
                out.append(Candidate(0, pos, kind, priority, seq))

        # 우선순위 : 우선 종류 → 상태 변경 직후 → 교란 종류 → 위치
        prefer = self.opts.prefer
        out.sort(key=lambda c: (
            c.kind not in prefer, prefer.index(c.kind) if c.kind in prefer else 0,
            not c.priority, KINDS.index(c.kind), c.position,
        ))
        for i, c in enumerate(out):
            c.index = i
        return out

    # 탐색
    def explore(self, scenario: Scenario) -> ExploreResult:
        oracles = self.oracles if self.oracles is not None else select_oracles(
            scenario.tags, self.driver, self.base_url
        )
        cands = self.candidates(scenario)
        attempts: list[Attempt] = []
        hits: list[Hit] = []
        runs = 0

        def attempt(idx: int, trial: int, sc: Scenario):
            nonlocal runs
            t = time.perf_counter()
            result = self.run_fn(sc)
            runs += 1
            status, verdicts = judge(result, oracles)
            attempts.append(Attempt(idx, trial, status, verdicts, int((time.perf_counter() - t) * 1000)))
            self.on_event("run_done", {"candidate": idx, "trial": trial, "status": status, "verdicts": verdicts})
            return status, verdicts, result

        def done(stopped: str) -> ExploreResult:
            ranked = sorted(hits, key=lambda h: (-h.hits / h.trials, h.candidate.index))
            limit = self.opts.top_n if self.opts.collect_all else 1
            return ExploreResult(scenario.name, len(cands), runs, ranked[:limit], attempts, stopped)

        # baseline : 교란 없이 통과해야 탐색 의미 있음
        self.on_event("baseline_start", {})
        status, _, _ = attempt(-1, 0, scenario)
        if status != "pass":
            return done(f"baseline_{status}")

        for c in cands:
            if runs >= self.opts.max_runs:
                return done("budget")
            self.on_event("candidate_start", {"candidate": c})
            sc = Scenario(scenario.name, scenario.tags, c.steps)
            hit_count, trials, first = 0, 0, None
            for trial in range(self.opts.k):
                if runs >= self.opts.max_runs:
                    break
                status, verdicts, result = attempt(c.index, trial, sc)
                trials += 1
                if status == "hit":
                    hit_count += 1
                    first = first or (verdicts, result)
                    if not self.opts.collect_all:
                        break
            if first:
                h = Hit(c, hit_count, trials, *first)
                hits.append(h)
                self.on_event("hit", {"hit": h})
                if not self.opts.collect_all:
                    return done("first_hit")
        return done("budget" if runs >= self.opts.max_runs else "exhausted")
