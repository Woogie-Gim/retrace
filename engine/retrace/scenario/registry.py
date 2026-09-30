"""스텝 레지스트리 : 스텝 정의는 한 번만 작성, 엔진·pytest-bdd 공유"""
from dataclasses import dataclass, field
from typing import Any, Callable

import parse

from ..driver import Driver


@dataclass
class StepContext:
    driver: Driver
    base_url: str
    vars: dict[str, Any] = field(default_factory=dict)  # 스텝 간 공유 값

    def url(self, path: str) -> str:
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")


@dataclass
class StepDef:
    pattern: str
    func: Callable[..., Any]

    def __post_init__(self):
        self.parser = parse.compile(self.pattern)

    @property
    def fields(self) -> list[str]:
        return list(self.parser.named_fields)

    def match(self, text: str) -> dict[str, Any] | None:
        # 전체 일치만 인정
        r = self.parser.parse(text)
        return None if r is None else dict(r.named)


class StepNotFound(LookupError):
    pass


class StepRegistry:
    def __init__(self):
        self.defs: list[StepDef] = []

    def add(self, pattern: str, func: Callable[..., Any]) -> StepDef:
        if any(d.pattern == pattern for d in self.defs):
            raise ValueError(f"중복 스텝 패턴: {pattern}")
        d = StepDef(pattern, func)
        self.defs.append(d)
        return d

    def step(self, pattern: str):
        def deco(func):
            self.add(pattern, func)
            return func
        return deco

    def match(self, text: str) -> tuple[StepDef, dict[str, Any]]:
        hits = [(d, kw) for d in self.defs if (kw := d.match(text)) is not None]
        if not hits:
            raise StepNotFound(f"일치하는 스텝 없음: {text}")
        if len(hits) > 1:
            raise StepNotFound(f"스텝 매칭 모호: {text} → {[d.pattern for d, _ in hits]}")
        return hits[0]

    def run(self, ctx: StepContext, text: str) -> Any:
        d, kw = self.match(text)
        return d.func(ctx, **kw)


# 전역 레지스트리
registry = StepRegistry()
step = registry.step
