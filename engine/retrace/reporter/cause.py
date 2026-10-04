"""원인 계층 분류 : dom·network·api 오라클 결과 + 로그 조합"""
from dataclasses import asdict, dataclass, field

from ..oracle import Verdict

BE = "BE"
FE = "FE"
UNKNOWN = "미분류"


@dataclass
class Cause:
    layer: str      # BE / FE / 미분류
    reason: str
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _api_url(e: dict) -> bool:
    return "/api/" in (e.get("url") or "")


def network_signals(logs: list[dict]) -> dict:
    # /api/ 오류 응답 + 클라이언트 측 요청 실패 (loadingFailed는 url 없음 → request_id로 연결)
    urls = {e["request_id"]: e.get("url") for e in logs if e.get("event") == "requestWillBeSent"}
    responses = [e for e in logs if e.get("event") == "responseReceived" and _api_url(e)]
    failed = [
        f"{e.get('error')} {urls.get(e.get('request_id'))}"
        for e in logs
        if e.get("event") == "loadingFailed" and "/api/" in (urls.get(e.get("request_id")) or "")
    ]
    return {
        "5xx": [f"{int(e['status'])} {e['url']}" for e in responses if (e.get("status") or 0) >= 500],
        "4xx": [f"{int(e['status'])} {e['url']}" for e in responses if 400 <= (e.get("status") or 0) < 500],
        "failed": failed,
    }


def classify(verdicts: list[Verdict], logs: dict) -> Cause:
    by_kind = {v.kind: v for v in verdicts}
    dom, api = by_kind.get("dom"), by_kind.get("api")
    net = network_signals(logs.get("network", []))
    severe = [e for e in logs.get("console", []) if e.get("level") == "SEVERE"]
    api_ok = api is not None and not api.hit and not api.detail.startswith("비교 불가")
    signals = {
        "dom": dom.detail if dom else None,
        "api": api.detail if api else None,
        "api_hit": bool(api and api.hit),
        "network": net,
        "console_severe": len(severe),
    }

    def out(layer: str, reason: str) -> Cause:
        return Cause(layer, reason, signals)

    if net["5xx"]:
        return out(BE, f"서버 5xx 응답: {net['5xx'][0]}")
    if api and api.hit:
        return out(FE, f"API 정상 + 화면 값 불일치 ({api.detail})")
    if dom and dom.hit and api_ok:
        return out(BE, f"API 값 이상 — 화면과 API가 같고 기대와 다름 ({api.detail})")
    if dom and dom.hit and not net["4xx"] and net["failed"]:
        return out(FE, f"API 오류 응답 없음 + 요청 중단 후 화면 처리 누락 ({net['failed'][0]})")
    if severe and not net["4xx"]:
        return out(FE, f"JS 콘솔 에러만 존재 ({(severe[0].get('message') or '')[:120]})")
    return out(UNKNOWN, "판단 근거 부족")
