"""DomOracle : Then 스텝 실패 = hit, Given/When 실패 = 무효 run"""
from ..scenario.runner import RunResult
from .base import Oracle, Verdict

PRIMARY = {"Given", "When", "Then"}


def effective_keywords(keywords: list[str]) -> list[str]:
    # And/But은 직전 주 키워드 상속
    out, last = [], "Given"
    for k in keywords:
        if k in PRIMARY:
            last = k
        out.append(last)
    return out


def failed_keyword(result: RunResult) -> str | None:
    if result.failed_at is None:
        return None
    return effective_keywords([s.keyword for s in result.steps])[result.failed_at]


class DomOracle(Oracle):
    kind = "dom"

    def check(self, result: RunResult) -> Verdict:
        if result.failed_at is None:
            return Verdict(False, self.kind, "Then 스텝 통과")
        step = result.steps[result.failed_at]
        error = (step.error or "").splitlines()[0] if step.error else ""
        return Verdict(True, self.kind, f"{step.keyword} {step.text} → {error}")
