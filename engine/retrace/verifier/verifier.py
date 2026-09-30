"""검증기 : 최소 스텝 반복 실행 → 재현율·등급"""
from dataclasses import asdict, dataclass, field
from typing import Callable

from ..explorer.explorer import judge
from ..oracle import Oracle
from ..scenario.parser import Scenario
from ..scenario.runner import RunResult

CONFIRMED = "확정"
INTERMITTENT = "간헐"
RARE = "희귀"
NOT_REPRODUCED = "미재현"
UNKNOWN = "판정불가"


def grade(hits: int, valid: int) -> str:
    # 유효 run(hit+pass) 기준 등급
    if valid == 0:
        return UNKNOWN
    rate = hits / valid
    if rate == 1:
        return CONFIRMED
    if rate >= 0.3:
        return INTERMITTENT
    return RARE if hits else NOT_REPRODUCED


@dataclass
class VerifyResult:
    runs: int
    hits: int
    passes: int
    invalid: int
    rate: float | None      # 유효 run 0회면 None
    grade: str
    fixed: bool | None = None  # expect_fixed 시 수정 확인 여부
    attempts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def verify(
    scenario: Scenario,
    run_fn: Callable[[Scenario], RunResult],
    oracles: list[Oracle],
    n: int = 10,
    expect_fixed: bool = False,
    on_event: Callable[[str, dict], None] | None = None,
) -> VerifyResult:
    on_event = on_event or (lambda name, data: None)
    counts = {"hit": 0, "pass": 0, "invalid": 0}
    attempts = []
    for i in range(n):
        status, verdicts = judge(run_fn(scenario), oracles)
        counts[status] += 1
        detail = next((f"{v.kind}: {v.detail}" for v in verdicts if v.hit), "")
        if status == "invalid" and verdicts:
            detail = verdicts[0].detail
        attempts.append({"trial": i, "status": status, "detail": detail})
        on_event("verify_progress", {"trial": i, "total": n, "status": status, "detail": detail})

    valid = counts["hit"] + counts["pass"]
    return VerifyResult(
        runs=n,
        hits=counts["hit"],
        passes=counts["pass"],
        invalid=counts["invalid"],
        rate=counts["hit"] / valid if valid else None,
        grade=grade(counts["hit"], valid),
        fixed=(counts["hit"] == 0 and valid > 0) if expect_fixed else None,
        attempts=attempts,
    )
