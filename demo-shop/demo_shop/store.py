"""인메모리 상태 저장소"""
import threading
import time
import uuid

from . import config

PRODUCTS = [
    {"id": 1, "name": "상품-1", "price": 30000},
    {"id": 2, "name": "상품-2", "price": 15000},
    {"id": 3, "name": "상품-3", "price": 8000},
]
PRODUCT_MAP = {p["id"]: p for p in PRODUCTS}

GRADES = {"normal": "일반", "silver": "실버", "gold": "골드"}

COUPONS = {
    "GOLD10": {"code": "GOLD10", "name": "10% 쿠폰", "rate": 0.10, "grades": ["gold"]},
    "SILVER5": {"code": "SILVER5", "name": "5% 쿠폰", "rate": 0.05, "grades": ["silver"]},
}

# 처리 지연 (초)
PRODUCTS_DELAY = 0.3
CART_DELAY = 0.15
ORDER_DELAY = 1.0

# 확률 버그 발생률
COUPON_BUG_RATE = 0.5
CART_CONFLICT_RATE = 0.3


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self._user_locks = {g: threading.Lock() for g in GRADES}
        self.reset()

    def reset(self):
        with self.lock:
            self.sessions: dict[str, str] = {}
            self.carts: dict[str, dict[int, int]] = {g: {} for g in GRADES}
            self.coupons: dict[str, list[str]] = {g: [] for g in GRADES}
            self.orders: list[dict] = []
            self.idem: dict[tuple[str, str], dict] = {}
            self.inflight: dict[tuple[str, int], int] = {}
            self._order_seq = 0

    # 인증
    def login(self, grade: str) -> str:
        if grade not in GRADES:
            raise ApiError(400, "알 수 없는 등급")
        token = uuid.uuid4().hex
        with self.lock:
            self.sessions[token] = grade
        return token

    def user_of(self, token: str | None) -> str:
        user = self.sessions.get(token or "")
        if not user:
            raise ApiError(401, "로그인 필요")
        return user

    def me(self, user: str) -> dict:
        coupons = [
            {"code": c["code"], "name": c["name"]}
            for c in COUPONS.values() if user in c["grades"]
        ]
        return {"grade": user, "grade_name": GRADES[user], "coupons": coupons}

    # 장바구니 (호출 측에서 lock 보유)
    def _cart_view(self, user: str) -> dict:
        items = []
        subtotal = 0
        for pid, qty in self.carts[user].items():
            p = PRODUCT_MAP[pid]
            items.append({"product_id": pid, "name": p["name"], "price": p["price"], "qty": qty})
            subtotal += p["price"] * qty
        total = subtotal
        for code in self.coupons[user]:
            total = round(total * (1 - COUPONS[code]["rate"]))
        return {
            "items": items,
            "subtotal": subtotal,
            "coupons": list(self.coupons[user]),
            "discount": subtotal - total,
            "total": total,
        }

    def cart_view(self, user: str) -> dict:
        with self.lock:
            return self._cart_view(user)

    def update_cart(self, user: str, pid: int, delta: int) -> dict:
        if pid not in PRODUCT_MAP:
            raise ApiError(404, "상품 없음")
        key = (user, pid)
        with self.lock:
            # 동시 수정 충돌 (타이밍 의존성을 확률로 모사, BUG_MODE 무관)
            if self.inflight.get(key, 0) > 0 and config.rng.random() < CART_CONFLICT_RATE:
                raise ApiError(409, "동시 수정 충돌")
            self.inflight[key] = self.inflight.get(key, 0) + 1
        try:
            time.sleep(CART_DELAY)
            with self.lock:
                cart = self.carts[user]
                qty = cart.get(pid, 0) + delta
                if qty > 0:
                    cart[pid] = qty
                else:
                    cart.pop(pid, None)
                return self._cart_view(user)
        finally:
            with self.lock:
                self.inflight[key] -= 1

    # 쿠폰
    def apply_coupon(self, user: str, code: str) -> dict:
        coupon = COUPONS.get(code)
        if not coupon or user not in coupon["grades"]:
            raise ApiError(400, "사용할 수 없는 쿠폰")
        with self.lock:
            applied = self.coupons[user]
            if code in applied:
                # BUG-02 : 적용 플래그 확인 누락 → 할인 중복 적용
                if config.BUG_MODE and config.rng.random() < COUPON_BUG_RATE:
                    applied.append(code)
                return self._cart_view(user)
            # 쿠폰은 1종만 적용
            self.coupons[user] = [code]
            return self._cart_view(user)

    # 주문
    def create_order(self, user: str, idem_key: str | None) -> dict:
        if config.BUG_MODE:
            # BUG-01 : 멱등성·락 없음 → 처리 지연 중 재요청 시 중복 주문
            return self._place_order(user)
        with self._user_locks[user]:
            if idem_key and (user, idem_key) in self.idem:
                return self.idem[(user, idem_key)]
            order = self._place_order(user)
            if idem_key:
                self.idem[(user, idem_key)] = order
            return order

    def _place_order(self, user: str) -> dict:
        view = self.cart_view(user)
        if not view["items"]:
            raise ApiError(400, "장바구니가 비어 있음")
        time.sleep(ORDER_DELAY)
        with self.lock:
            self._order_seq += 1
            order = {
                "id": self._order_seq,
                "items": view["items"],
                "subtotal": view["subtotal"],
                "discount": view["discount"],
                "total": view["total"],
                "coupons": view["coupons"],
            }
            self.orders.append({**order, "user": user})
            self.carts[user] = {}
            self.coupons[user] = []
            return order

    def list_orders(self, user: str) -> list[dict]:
        with self.lock:
            return [
                {k: v for k, v in o.items() if k != "user"}
                for o in self.orders if o["user"] == user
            ]


store = Store()
