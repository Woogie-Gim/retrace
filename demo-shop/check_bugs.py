"""Phase 1 완료 기준 확인 : 버그 4종 on/off 발생 횟수 출력

사용법 (저장소 루트 기준)
  engine/.venv/Scripts/python demo-shop/check_bugs.py
  engine/.venv/Scripts/python demo-shop/check_bugs.py --runs 20 --seed 42
  engine/.venv/Scripts/python demo-shop/check_bugs.py --on-url http://127.0.0.1:5101 --off-url http://127.0.0.1:5102
"""
import argparse
import os
import statistics
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import requests

SHOP_DIR = Path(__file__).resolve().parent
EXPECTED_TOTAL = 27000  # 상품-1 30000원 + 10% 쿠폰
FE_TIMEOUT_MS = 2000    # products.html 버그 모드 타임아웃


# 서버 기동·종료
def start_server(mode: str, port: int, seed: str) -> subprocess.Popen:
    env = {**os.environ, "BUG_MODE": mode, "BUG_SEED": seed, "DEMO_SHOP_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, "-m", "demo_shop"],
        cwd=SHOP_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_ready(base: str, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return requests.get(base + "/api/config", timeout=1).json()
        except requests.RequestException:
            time.sleep(0.3)
    raise RuntimeError(f"서버 응답 없음: {base}")


# 공통 준비 : 초기화 → 골드 로그인 → 상품-1 담기
def prepare(base: str) -> str:
    requests.post(base + "/api/reset").raise_for_status()
    s = requests.Session()
    s.post(base + "/api/login", json={"grade": "gold"}).raise_for_status()
    s.post(base + "/api/cart", json={"product_id": 1, "delta": 1}).raise_for_status()
    return s.cookies.get("session")


def get(base: str, token: str, path: str):
    return requests.get(base + path, cookies={"session": token}).json()


def concurrent_posts(base: str, token: str, path: str, n: int, **kwargs) -> list[int]:
    # 스레드별 요청, Barrier로 시작 시점 정렬
    barrier = threading.Barrier(n)
    codes: list[int] = []

    def worker():
        barrier.wait()
        r = requests.post(base + path, cookies={"session": token}, **kwargs)
        codes.append(r.status_code)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return codes


# BUG-01 : 같은 멱등성 키로 결제 동시 2건
def bug01(base: str, bug_mode: bool) -> bool:
    token = prepare(base)
    key = str(uuid.uuid4())
    concurrent_posts(base, token, "/api/orders", 2, headers={"Idempotency-Key": key})
    return len(get(base, token, "/api/orders")) >= 2


# BUG-02 : 쿠폰 재적용 (뒤로가기 후 재적용 모사)
def bug02(base: str, bug_mode: bool) -> bool:
    token = prepare(base)
    for _ in range(2):
        requests.post(
            base + "/api/coupons/apply", json={"code": "GOLD10"}, cookies={"session": token}
        ).raise_for_status()
    return get(base, token, "/api/cart")["total"] != EXPECTED_TOTAL


# BUG-04 : 수량 +1 연속 2회, 모드별 FE 요청 방식 모사
def bug04(base: str, bug_mode: bool) -> bool:
    token = prepare(base)
    body = {"product_id": 1, "delta": 1}
    if bug_mode:
        # 병렬 요청 + 낙관적 반영 (롤백 없음)
        concurrent_posts(base, token, "/api/cart", 2, json=body)
        screen = 1 + 2
    else:
        # 직렬 요청 + 응답 수량 동기화
        cart = None
        for _ in range(2):
            cart = requests.post(base + "/api/cart", json=body, cookies={"session": token}).json()
        screen = cart["items"][0]["qty"]
    server = get(base, token, "/api/cart")["items"][0]["qty"]
    return screen != server


# BUG-03 : 상품 목록 응답 지연 측정
def bug03_latency(base: str, runs: int) -> list[float]:
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        requests.get(base + "/api/products").raise_for_status()
        times.append((time.perf_counter() - t) * 1000)
    return times


def check(label: str, base: str, runs: int) -> dict[str, int]:
    bug_mode = wait_ready(base)["bug_mode"]
    counts = {}
    for name, fn in [("BUG-01", bug01), ("BUG-02", bug02), ("BUG-04", bug04)]:
        counts[name] = sum(fn(base, bug_mode) for _ in range(runs))
    lat = bug03_latency(base, runs)
    hits = "  ".join(f"{k} {v:>2}/{runs}" for k, v in counts.items())
    print(
        f"[{label}] bug_mode={'on' if bug_mode else 'off'}  {hits}  "
        f"BUG-03 avg {statistics.mean(lat):.0f}ms max {max(lat):.0f}ms (FE timeout {FE_TIMEOUT_MS}ms)"
    )
    return counts


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 1 버그 발생 확인")
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--seed", default="42")
    p.add_argument("--on-url", help="이미 기동된 BUG_MODE=on 서버")
    p.add_argument("--off-url", help="이미 기동된 BUG_MODE=off 서버")
    args = p.parse_args()

    procs = []
    try:
        on_url, off_url = args.on_url, args.off_url
        if not on_url:
            procs.append(start_server("on", 5101, args.seed))
            on_url = "http://127.0.0.1:5101"
        if not off_url:
            procs.append(start_server("off", 5102, args.seed))
            off_url = "http://127.0.0.1:5102"

        on = check("on ", on_url, args.runs)
        off = check("off", off_url, args.runs)
    finally:
        for proc in procs:
            proc.terminate()
            proc.wait(timeout=10)

    print("참고 : BUG-04는 모드별 FE 요청 방식을 모사, BUG-03은 지연만 측정 (빈 화면은 브라우저 스로틀링 필요)")
    passed = all(v > 0 for v in on.values()) and all(v == 0 for v in off.values())
    print(f"결과 : {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
