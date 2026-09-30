"""최소화기 : hit 시퀀스에서 ddmin으로 불필요 스텝 제거"""
from dataclasses import asdict, dataclass, field, replace
from typing import Callable, Sequence, TypeVar

from ..explorer.explorer import judge
from ..oracle import Oracle
from ..oracle.dom import effective_keywords
from ..scenario.parser import Scenario, Step
from ..scenario.runner import RunResult

T = TypeVar("T")


def _split(items: list[T], n: int) -> list[list[T]]:
    # n개 연속 조각으로 균등 분할
    size, rest = divmod(len(items), n)
    out, start = [], 0
    for i in range(n):
        end = start + size + (1 if i < rest else 0)
        out.append(items[start:end])
        start = end
    return out


def ddmin(items: Sequence[T], test: Callable[[list[T]], bool]) -> list[T]:
    """test(items)가 참이라는 전제에서 참을 유지하는 1-최소 부분집합"""
    cache: dict[tuple, bool] = {}

    def t(sub: list[T]) -> bool:
        key = tuple(sub)
        if key not in cache:
            cache[key] = test(sub)
        return cache[key]

    items, n = list(items), 2
    while len(items) >= 2:
        chunks = _split(items, n)
        # 조각만 남겨 hit → 그 조각으로
        nxt = next((c for c in chunks if t(c)), None)
        if nxt is not None:
            items, n = nxt, 2
            continue
        # 조각을 빼고 hit → 여집합으로
        for i in range(len(chunks)):
            comp = [x for j, c in enumerate(chunks) if j != i for x in c]
            if t(comp):
                items, n = comp, max(n - 1, 2)
                break
        else:
            if n >= len(items):
                break
            n = min(n * 2, len(items))
    return items


@dataclass
class Probe:
    steps: list[str]    # 후보 시퀀스 스텝 문장
    outcome: str        # hit / no_hit / control_fail / no_perturbation
    runs: int
    detail: str = ""


@dataclass
class MinimizeResult:
    scenario: str
    original: list[Step]
    minimized: list[Step]
    runs: int
    stopped: str        # minimized / not_reproduced
    probes: list[Probe] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "stopped": self.stopped,
            "runs": self.runs,
            "original_count": len(self.original),
            "minimized_count": len(self.minimized),
            "original": [asdict(s) for s in self.original],
            "minimized": [asdict(s) for s in self.minimized],
            "probes": [asdict(p) for p in self.probes],
        }


def normalize(steps: list[Step]) -> list[Step]:
    # Background 뒤 첫 스텝이 And/But이면 When으로
    out = list(steps)
    i = next((i for i, s in enumerate(out) if not s.background), None)
    if i is not None and out[i].keyword in ("And", "But"):
        out[i] = replace(out[i], keyword="When")
    return out


class Minimizer:
    def __init__(
        self,
        run_fn: Callable[[Scenario], RunResult],
        oracles: list[Oracle],
        k: int = 3,
        on_event: Callable[[str, dict], None] | None = None,
    ):
        self.run_fn = run_fn
        self.oracles = oracles
        self.k = k
        self.on_event = on_event or (lambda name, data: None)

    def minimize(self, scenario: Scenario) -> MinimizeResult:
        steps = scenario.steps
        eff = effective_keywords([s.keyword for s in steps])
        # Background·Then 고정, 나머지만 제거 대상
        fixed = {i for i, s in enumerate(steps) if s.background or eff[i] == "Then"}
        removable = [i for i in range(len(steps)) if i not in fixed]
        records: list[Probe] = []
        controls: dict[tuple, tuple[str, str]] = {}
        runs = 0

        def build(sub: list[int]) -> list[Step]:
            keep = fixed | set(sub)
            return normalize([s for i, s in enumerate(steps) if i in keep])

        def run(seq: list[Step]) -> tuple[str, str]:
            nonlocal runs
            result = self.run_fn(Scenario(scenario.name, scenario.tags, seq))
            runs += 1
            status, verdicts = judge(result, self.oracles)
            hits = [f"{v.kind}: {v.detail}" for v in verdicts if v.hit]
            detail = hits[0] if hits else (verdicts[0].detail if status == "invalid" and verdicts else "")
            return status, detail

        def control(seq: list[Step]) -> tuple[str, str]:
            # 교란 제외 시퀀스 결과 캐시
            key = tuple((s.keyword, s.text) for s in seq)
            if key not in controls:
                controls[key] = run(seq)
            return controls[key]

        def test(sub: list[int]) -> bool:
            seq = build(sub)
            before = runs
            rec = Probe([s.text for s in seq], "no_hit", 0)
            if not any(s.perturbation for s in seq):
                rec.outcome = "no_perturbation"
            else:
                # 대조 : 교란만 빼면 통과해야 교란이 원인
                status, detail = control(normalize([s for s in seq if not s.perturbation]))
                if status != "pass":
                    rec.outcome, rec.detail = "control_fail", f"대조 {status} {detail}".strip()
                else:
                    # k회 중 1회라도 hit, invalid는 판정 제외
                    for _ in range(self.k):
                        status, detail = run(seq)
                        if status == "hit":
                            rec.outcome, rec.detail = "hit", detail
                            break
                        if status == "invalid":
                            rec.detail = detail
            rec.runs = runs - before
            records.append(rec)
            self.on_event("minimize_step", {"record": rec, "size": len(seq)})
            return rec.outcome == "hit"

        if not test(removable):
            return MinimizeResult(scenario.name, steps, steps, runs, "not_reproduced", records)
        best = ddmin(removable, test)
        return MinimizeResult(scenario.name, steps, build(best), runs, "minimized", records)
