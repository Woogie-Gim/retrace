"""교란 카탈로그 : 삽입 위치의 직전 스텝을 보고 교란 스텝 생성"""
from dataclasses import dataclass, field

from ..scenario.parser import Step
from ..scenario.registry import StepNotFound, StepRegistry

# 교란 종류 (정렬 순서)
KINDS = ["rapid_click", "back", "refresh", "network", "resize", "boundary"]

CLICK_PATTERN = '"{target}" 버튼을 누르면'

# 경계값 기본 목록
BOUNDARY_VALUES = ["", "0", "-1", "999999999999", "<b>x</b>"]


@dataclass
class CatalogOptions:
    rapid_times: int = 3
    network_profiles: tuple[str, ...] = ("slow-3g",)  # offline은 정상 앱도 실패 → 기본 제외
    sizes: tuple[tuple[int, int], ...] = ((375, 667),)
    fields: dict[str, list[str]] = field(default_factory=dict)  # 경계값 대상 필드 → 값 목록 (빈 목록 = 기본값)


def _p(text: str, kind: str) -> Step:
    return Step("And", text, perturbation=kind)


def _lookup(registry: StepRegistry, step: Step | None):
    if step is None:
        return None, {}
    try:
        return registry.match(step.text)
    except StepNotFound:
        return None, {}


def perturbations(prev: Step | None, registry: StepRegistry, opts: CatalogOptions) -> list[tuple[str, list[Step]]]:
    """(교란 종류, 삽입할 스텝 목록) 리스트"""
    d, kw = _lookup(registry, prev)
    out: list[tuple[str, list[Step]]] = []

    # 연타 : 직전 스텝이 버튼 클릭이면 같은 버튼
    if d is not None and d.pattern == CLICK_PATTERN:
        text = f'"{kw["target"]}" 버튼을 빠르게 {opts.rapid_times}회 누르면'
        out.append(("rapid_click", [_p(text, "rapid_click")]))

    # 뒤로가기 : 직전 스텝이 멱등이면 재실행으로 흐름 복귀 (재사용 결함 노림)
    back = [_p("브라우저 뒤로가기를 하면", "back")]
    if d is not None and d.idempotent:
        back.append(Step("And", prev.text, perturbation="replay"))
    out.append(("back", back))

    out.append(("refresh", [_p("페이지를 새로고침하면", "refresh")]))
    for profile in opts.network_profiles:
        out.append(("network", [_p(f'네트워크를 "{profile}" 상태로 바꾸면', "network")]))
    for w, h in opts.sizes:
        out.append(("resize", [_p(f"창 크기를 {w}x{h}로 바꾸면", "resize")]))
    for name, values in opts.fields.items():
        for v in values or BOUNDARY_VALUES:
            out.append(("boundary", [_p(f'"{name}"에 "{v}"를 입력하면', "boundary")]))
    return out
