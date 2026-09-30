from ..driver import Driver
from .api import ApiOracle
from .base import Oracle, Verdict
from .console import ConsoleOracle
from .dom import DomOracle, failed_keyword
from .network import NetworkOracle


def select_oracles(tags: list[str], driver: Driver, base_url: str) -> list[Oracle]:
    # DomOracle 항상 + 태그로 활성화
    oracles: list[Oracle] = [DomOracle(), ConsoleOracle(), NetworkOracle(), ApiOracle(driver, base_url)]
    return [o for o in oracles if o.tag is None or o.tag in tags]


__all__ = [
    "Oracle", "Verdict", "DomOracle", "ConsoleOracle", "NetworkOracle", "ApiOracle",
    "failed_keyword", "select_oracles",
]
