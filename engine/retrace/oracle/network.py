"""NetworkOracle : 4xx·5xx 응답"""
from ..scenario.runner import RunResult
from .base import Oracle, Verdict


class NetworkOracle(Oracle):
    kind = "network"
    tag = "@oracle-network"

    def check(self, result: RunResult) -> Verdict:
        bad = [
            e for e in result.logs.get("network", [])
            if e.get("event") == "responseReceived" and (e.get("status") or 0) >= 400
        ]
        if not bad:
            return Verdict(False, self.kind, "4xx·5xx 없음")
        head = "; ".join(f"{int(e['status'])} {e.get('url')}" for e in bad[:3])
        return Verdict(True, self.kind, f"오류 응답 {len(bad)}건: {head}")
