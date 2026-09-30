"""Driver 인터페이스 : Explorer 이후 단계는 이 인터페이스만 사용"""
from abc import ABC, abstractmethod


class Driver(ABC):
    # 공통 조작
    @abstractmethod
    def open(self, url: str) -> None: ...
    @abstractmethod
    def click(self, target: str, times: int = 1, interval_ms: int = 0) -> None: ...
    @abstractmethod
    def type(self, target: str, value: str) -> None: ...
    @abstractmethod
    def text_of(self, target: str) -> str: ...
    # 교란 조작
    @abstractmethod
    def back(self) -> None: ...
    @abstractmethod
    def refresh(self) -> None: ...
    @abstractmethod
    def set_network(self, profile: str) -> None: ...
    @abstractmethod
    def resize(self, w: int, h: int) -> None: ...
    # 증거 수집
    @abstractmethod
    def screenshot(self, path: str) -> None: ...
    @abstractmethod
    def console_logs(self) -> list[dict]: ...
    @abstractmethod
    def network_logs(self) -> list[dict]: ...

    # 자원 정리 (필요한 구현만 재정의)
    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
