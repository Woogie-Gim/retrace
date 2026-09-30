"""스텝 레지스트리 : 스텝 정의는 한 번만 작성, 엔진·pytest-bdd 공유"""
import itertools
import re
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


# 조사 선택 표기 : (을|를) / (이|가) 등 한 글자 대안
JOSA_ALT = re.compile(r"\((\w)\|(\w)\)")


def expand_pattern(pattern: str) -> list[str]:
    # 조사 대안 조합별 패턴 전개
    parts = JOSA_ALT.split(pattern)
    literals, alts = parts[0::3], list(zip(parts[1::3], parts[2::3]))
    out = []
    for combo in itertools.product(*alts):
        out.append(literals[0] + "".join(c + lit for c, lit in zip(combo, literals[1:])))
    return out


@dataclass
class StepDef:
    pattern: str
    func: Callable[..., Any]
    idempotent: bool = False  # 재실행해도 결과가 같아야 하는 스텝 (뒤로가기 후 재실행 후보)

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

    def add(self, pattern: str, func: Callable[..., Any], idempotent: bool = False) -> list[StepDef]:
        added = []
        for p in expand_pattern(pattern):
            if any(d.pattern == p for d in self.defs):
                raise ValueError(f"중복 스텝 패턴: {p}")
            d = StepDef(p, func, idempotent)
            self.defs.append(d)
            added.append(d)
        return added

    def step(self, pattern: str, idempotent: bool = False):
        def deco(func):
            self.add(pattern, func, idempotent)
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
