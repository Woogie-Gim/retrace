"""ApiOracle : 현재 화면 값과 API 값 대조 (데모 쇼핑몰 전용)"""
import time

from ..driver import Driver
from ..scenario.runner import RunResult
from ..steps.shop import amount
from ..steps.shop_api import ShopApi
from .base import Oracle, Verdict

SETTLE_SEC = 0.5  # 진행 중 요청 완료 대기


class ApiOracle(Oracle):
    kind = "api"
    tag = "@oracle-api"

    def __init__(self, driver: Driver, base_url: str):
        self.driver = driver
        self.base_url = base_url

    def check(self, result: RunResult) -> Verdict | None:
        grade = result.vars.get("grade")
        if not grade:
            return None
        time.sleep(SETTLE_SEC)
        try:
            title = self.driver.text_of("css=h1")
            api = ShopApi(self.base_url, grade)
            if title.startswith("장바구니"):
                return self._cart(api)
            if title.startswith("주문 내역"):
                return self._orders(api)
            if title.startswith("결제"):
                return self._checkout(api)
        except Exception as e:
            return Verdict(False, self.kind, f"비교 불가: {type(e).__name__}")
        return None

    def _cart(self, api: ShopApi) -> Verdict:
        diffs, parts = [], []
        for item in api.cart()["items"]:
            screen = amount(self.driver.text_of(f"cart-qty-{item['product_id']}"))
            parts.append(f"{item['name']} 화면 {screen} / API {item['qty']}")
            if screen != item["qty"]:
                diffs.append(parts[-1])
        if diffs:
            return Verdict(True, self.kind, "장바구니 수량 불일치: " + ", ".join(diffs))
        return Verdict(False, self.kind, "장바구니 일치: " + (", ".join(parts) or "비어 있음"))

    def _orders(self, api: ShopApi) -> Verdict:
        orders = api.orders()
        screen_count = amount(self.driver.text_of("order-count"))
        detail = f"주문 화면 {screen_count}건 / API {len(orders)}건"
        if screen_count != len(orders):
            return Verdict(True, self.kind, "주문 건수 불일치: " + detail)
        if orders:
            screen_total = amount(self.driver.text_of(f"order-total-{orders[-1]['id']}"))
            detail += f", 최근 금액 화면 {screen_total} / API {orders[-1]['total']}"
            if screen_total != orders[-1]["total"]:
                return Verdict(True, self.kind, "주문 금액 불일치: " + detail)
        return Verdict(False, self.kind, "주문 일치: " + detail)

    def _checkout(self, api: ShopApi) -> Verdict:
        total = api.cart()["total"]
        screen = amount(self.driver.text_of("checkout-total"))
        detail = f"결제 금액 화면 {screen} / API {total}"
        return Verdict(screen != total, self.kind, ("결제 금액 불일치: " if screen != total else "결제 금액 일치: ") + detail)
