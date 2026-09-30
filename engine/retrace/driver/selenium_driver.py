"""Selenium(Chrome) 기반 Driver 구현"""
import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .. import config
from .base import Driver

# CDP 네트워크 조건 (throughput 단위 : bytes/s, -1 = 제한 없음)
NETWORK_PROFILES = {
    "fast": {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1},
    "slow-3g": {"offline": False, "latency": 400, "downloadThroughput": 50_000, "uploadThroughput": 50_000},
    "offline": {"offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0},
}

# 네트워크 로그로 남길 CDP 이벤트
NETWORK_EVENTS = {"Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFailed"}


def locator(target: str) -> tuple[str, str]:
    # css= / xpath= 접두어 외에는 data-testid로 해석
    if target.startswith("css="):
        return By.CSS_SELECTOR, target[4:]
    if target.startswith("xpath="):
        return By.XPATH, target[6:]
    return By.CSS_SELECTOR, f'[data-testid="{target}"]'


class SeleniumDriver(Driver):
    def __init__(self, headless: bool | None = None, timeout: float = 10, window: tuple[int, int] = (1280, 800)):
        opts = webdriver.ChromeOptions()
        if config.HEADLESS if headless is None else headless:
            opts.add_argument("--headless=new")
        opts.add_argument(f"--window-size={window[0]},{window[1]}")
        opts.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
        self.wd = webdriver.Chrome(options=opts)
        self.timeout = timeout
        self.wd.execute_cdp_cmd("Network.enable", {})

    # 요소 탐색
    def _wait(self, condition):
        return WebDriverWait(self.wd, self.timeout).until(condition)

    # 공통 조작
    def open(self, url: str) -> None:
        self.wd.get(url)

    def click(self, target: str, times: int = 1, interval_ms: int = 0) -> None:
        el = self._wait(EC.element_to_be_clickable(locator(target)))
        for i in range(times):
            el.click()
            if interval_ms and i < times - 1:
                time.sleep(interval_ms / 1000)

    def type(self, target: str, value: str) -> None:
        el = self._wait(EC.visibility_of_element_located(locator(target)))
        if el.tag_name.lower() == "select":
            # 옵션 로딩 대기 후 표시 텍스트 → value 순으로 선택
            select = Select(el)
            self._wait(lambda _: len(select.options) > 0)
            try:
                select.select_by_visible_text(value)
            except NoSuchElementException:
                select.select_by_value(value)
            return
        el.clear()
        el.send_keys(value)

    def text_of(self, target: str) -> str:
        return self._wait(EC.visibility_of_element_located(locator(target))).text

    # 교란 조작
    def back(self) -> None:
        self.wd.back()

    def refresh(self) -> None:
        self.wd.refresh()

    def set_network(self, profile: str) -> None:
        if profile not in NETWORK_PROFILES:
            raise ValueError(f"알 수 없는 네트워크 프로필: {profile}")
        self.wd.execute_cdp_cmd("Network.emulateNetworkConditions", NETWORK_PROFILES[profile])

    def resize(self, w: int, h: int) -> None:
        self.wd.set_window_size(w, h)

    # 증거 수집
    def screenshot(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.wd.save_screenshot(str(path))

    def console_logs(self) -> list[dict]:
        # 조회 시 버퍼 비워짐
        return [
            {
                "level": e.get("level"),
                "message": e.get("message"),
                "source": e.get("source"),
                "timestamp": e.get("timestamp"),
            }
            for e in self.wd.get_log("browser")
        ]

    def network_logs(self) -> list[dict]:
        # performance 로그에서 요청·응답·실패 이벤트만 정규화
        logs = []
        for entry in self.wd.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method")
            if method not in NETWORK_EVENTS:
                continue
            p = msg.get("params", {})
            req = p.get("request", {})
            res = p.get("response", {})
            logs.append({
                "event": method.split(".", 1)[1],
                "request_id": p.get("requestId"),
                "method": req.get("method"),
                "url": req.get("url") or res.get("url"),
                "status": res.get("status"),
                "type": p.get("type"),
                "error": p.get("errorText"),
                "timestamp": entry.get("timestamp"),
            })
        return logs

    def close(self) -> None:
        self.wd.quit()
