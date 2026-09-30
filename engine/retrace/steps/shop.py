"""데모 쇼핑몰 스텝"""
import re
import time

from ..scenario.registry import StepContext, step
from .shop_api import GRADE_CODES, ShopApi

# 화면 라벨 → data-testid (없으면 입력값을 testid로 사용)
TARGETS = {
    "로그인": "login-submit",
    "주문하기": "go-coupon",
    "적용": "coupon-apply",
    "쿠폰 없이 결제하기": "skip-coupon",
    "결제": "pay-button",
    "다시 시도": "retry",
    **{f"상품-{i} 수량 증가": f"qty-inc-{i}" for i in range(1, 4)},
    **{f"상품-{i} 수량 감소": f"qty-dec-{i}" for i in range(1, 4)},
}

# 화면 이름 → 경로
PAGES = {
    "로그인": "/login.html",
    "상품 목록": "/products.html",
    "장바구니": "/cart.html",
    "쿠폰": "/coupon.html",
    "결제": "/checkout.html",
    "주문 내역": "/orders.html",
}

# Then 대기 (느린 네트워크 교란 감안)
THEN_TIMEOUT = 30
NAV_TIMEOUT = 15
SETTLE_SEC = 0.5


def resolve(target: str) -> str:
    return TARGETS.get(target, target)


def wait_until(fn, timeout: float = 10, interval: float = 0.1):
    # fn이 참 값을 반환할 때까지 재시도
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            value = fn()
            if value:
                return value
        except Exception as e:
            last_err = e
        time.sleep(interval)
    raise TimeoutError(f"대기 시간 초과: {last_err or '조건 불충족'}")


def amount(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        raise ValueError(f"금액 아님: {text!r}")
    return int(digits)


@step('"{grade}" 등급 회원으로 로그인하면')
def login(ctx: StepContext, grade):
    # 등급 선택은 표시 텍스트 기준 (일반/실버/골드)
    ctx.driver.open(ctx.url("/login.html"))
    ctx.driver.type("login-grade", grade)
    ctx.driver.click("login-submit")
    wait_until(lambda: grade in ctx.driver.text_of("nav-user"))
    ctx.vars["grade"] = GRADE_CODES.get(grade, grade)


@step('"{product}"(을|를) 장바구니에 담으면')
def add_to_cart(ctx: StepContext, product):
    ctx.driver.open(ctx.url("/products.html"))
    ctx.driver.click(
        "xpath=//*[starts-with(@data-testid,'product-item-')]"
        f"[.//*[normalize-space(text())='{product}']]//button"
    )
    wait_until(lambda: product in ctx.driver.text_of("toast"))


@step('"{coupon}"(을|를) 적용하면', idempotent=True)
def apply_coupon(ctx: StepContext, coupon):
    ctx.driver.open(ctx.url("/coupon.html"))
    ctx.driver.type("coupon-select", coupon)
    ctx.driver.click("coupon-apply")
    # 적용 성공 시 결제 화면 이동
    wait_until(lambda: "원" in ctx.driver.text_of("checkout-total"))


@step('"{target}" 버튼을 누르면')
def click(ctx: StepContext, target):
    ctx.driver.click(resolve(target))


@step('"{page}" 화면을 열면')
def open_page(ctx: StepContext, page):
    ctx.driver.open(ctx.url(PAGES[page]))
    # 데모 쇼핑몰 화면 로드 확인
    ctx.driver.text_of("css=h1")


def open_orders(ctx: StepContext) -> str:
    # 결제 후 자연 이동 대기 → settle → 재조회 (교란으로 다른 화면이어도 같은 기준)
    try:
        wait_until(lambda: ctx.driver.text_of("order-count"), timeout=NAV_TIMEOUT)
    except TimeoutError:
        pass
    time.sleep(SETTLE_SEC)
    ctx.driver.open(ctx.url("/orders.html"))
    return wait_until(lambda: ctx.driver.text_of("order-count"), timeout=THEN_TIMEOUT)


@step('결제 금액은 "{expected}"원이다')
def order_total_is(ctx: StepContext, expected):
    # 가장 최근 주문 금액 (주문 내역 화면)
    open_orders(ctx)
    text = ctx.driver.text_of("xpath=(//*[starts-with(@data-testid,'order-total-')])[last()]")
    actual = amount(text)
    assert actual == amount(expected), f"결제 금액 {actual} != 기대 {expected}"


@step('주문 내역은 "{n}"건이다')
def order_count_is(ctx: StepContext, n):
    actual = amount(open_orders(ctx))
    assert actual == int(n), f"주문 {actual}건 != 기대 {n}건"


@step('상품 목록에 "{product}"(이|가) 보인다')
def product_visible(ctx: StepContext, product):
    # 상품 목록 화면이 아니면 새로 열어 확인 (교란으로 이동한 경우)
    if not ctx.driver.text_of("css=h1").startswith("상품 목록"):
        ctx.driver.open(ctx.url(PAGES["상품 목록"]))
    target = f"xpath=//*[starts-with(@data-testid,'product-name-')][normalize-space(text())='{product}']"
    try:
        wait_until(lambda: ctx.driver.text_of(target), timeout=THEN_TIMEOUT)
    except TimeoutError:
        raise AssertionError(f"상품 목록에 {product} 없음") from None


def cart_diff(ctx: StepContext, api: ShopApi) -> list[str]:
    # 화면 수량과 서버 수량 차이 목록
    diffs = []
    for item in api.cart()["items"]:
        screen = amount(ctx.driver.text_of(f"cart-qty-{item['product_id']}"))
        if screen != item["qty"]:
            diffs.append(f"{item['name']} 화면 {screen} / 서버 {item['qty']}")
    return diffs


@step("장바구니 화면 수량이 서버와 일치한다")
def cart_matches_server(ctx: StepContext):
    # 장바구니 화면이 아니면 새로 열어 비교
    if not ctx.driver.text_of("css=h1").startswith("장바구니"):
        ctx.driver.open(ctx.url(PAGES["장바구니"]))
    api = ShopApi(ctx.base_url, ctx.vars["grade"])
    diffs: list[str] = []

    def same():
        nonlocal diffs
        diffs = cart_diff(ctx, api)
        return not diffs

    try:
        wait_until(same, timeout=10, interval=0.3)
    except TimeoutError:
        raise AssertionError("장바구니 수량 불일치: " + ", ".join(diffs)) from None
