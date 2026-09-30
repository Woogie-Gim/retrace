"""Oracle 공통 : 판정 결과 + 태그 기반 활성화"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..scenario.runner import RunResult


@dataclass
class Verdict:
    hit: bool
    kind: str      # console / network / dom / api
    detail: str


class Oracle(ABC):
    kind: str = ""
    tag: str | None = None  # 활성화 태그 (None = 항상)

    @abstractmethod
    def check(self, result: RunResult) -> Verdict | None:
        """판정 대상 아니면 None"""
