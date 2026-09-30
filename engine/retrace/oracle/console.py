"""ConsoleOracle : SEVERE 레벨 콘솔 에러"""
from ..scenario.runner import RunResult
from .base import Oracle, Verdict


class ConsoleOracle(Oracle):
    kind = "console"
    tag = "@oracle-console"

    def check(self, result: RunResult) -> Verdict:
        errors = [e for e in result.logs.get("console", []) if e.get("level") == "SEVERE"]
        if not errors:
            return Verdict(False, self.kind, "SEVERE 없음")
        head = "; ".join((e.get("message") or "")[:120] for e in errors[:3])
        return Verdict(True, self.kind, f"SEVERE {len(errors)}건: {head}")
