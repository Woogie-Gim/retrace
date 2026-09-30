"""데모 쇼핑몰 API 조회 클라이언트 (스텝·ApiOracle 공용)

스토어가 등급 단위로 장바구니·주문을 보관 → 같은 등급 별도 로그인으로 동일 데이터 조회
"""
import requests

# 화면 등급명 → API 등급 코드
GRADE_CODES = {"일반": "normal", "실버": "silver", "골드": "gold"}


class ShopApi:
    def __init__(self, base_url: str, grade: str, timeout: float = 5):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        code = GRADE_CODES.get(grade, grade)
        self.s.post(self.base + "/api/login", json={"grade": code}, timeout=timeout).raise_for_status()

    def _get(self, path: str):
        r = self.s.get(self.base + path, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def cart(self) -> dict:
        return self._get("/api/cart")

    def orders(self) -> list[dict]:
        return self._get("/api/orders")
