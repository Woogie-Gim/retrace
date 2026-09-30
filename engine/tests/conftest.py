"""공용 픽스처 + pytest-bdd 어댑터 등록"""
import subprocess
import sys
import time
from urllib.parse import urlparse

import pytest
import requests

from retrace import config, steps  # noqa: F401  스텝 등록
from retrace.driver import SeleniumDriver
from retrace.scenario.bdd import register_pytest_bdd
from retrace.scenario.registry import StepContext
from retrace.scenario.runner import reset_target

SHOP_DIR = config.ROOT_DIR / "demo-shop"

# 레지스트리 스텝 → 이 모듈에 pytest-bdd 스텝 픽스처 주입
register_pytest_bdd()


def _alive(base: str) -> bool:
    try:
        return requests.get(base + "/api/config", timeout=1).ok
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def base_url():
    base = config.BASE_URL
    if _alive(base):
        yield base
        return
    # 미기동 시 demo-shop 직접 기동
    port = urlparse(base).port or config.DEMO_SHOP_PORT
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "demo_shop.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=SHOP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 15
        while not _alive(base):
            if time.time() > deadline or proc.poll() is not None:
                pytest.fail(f"demo-shop 기동 실패: {base}")
            time.sleep(0.3)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def driver():
    with SeleniumDriver() as d:
        yield d


@pytest.fixture
def ctx(driver, base_url):
    reset_target(base_url)
    return StepContext(driver=driver, base_url=base_url)
