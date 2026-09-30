"""데모 쇼핑몰 스텝"""
import re
import time

from ..scenario.registry import StepContext, step

# 화면 라벨 → data-testid (없으면 입력값을 testid로 사용)
TARGETS = {
    "로그인": "login-submit",
    "주문하기": "go-coupon",
    "적용": "coupon-apply",
    "쿠폰 없이 결제하기": "skip-coupon",
    "결제": "pay-button",
    "다시 시도": "retry",
}


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


@step('"{product}"을 장바구니에 담으면')
def add_to_cart(ctx: StepContext, product):
    ctx.driver.open(ctx.url("/products.html"))
    ctx.driver.click(
        "xpath=//*[starts-with(@data-testid,'product-item-')]"
        f"[.//*[normalize-space(text())='{product}']]//button"
    )
    wait_until(lambda: product in ctx.driver.text_of("toast"))


@step('"{coupon}"을 적용하면')
def apply_coupon(ctx: StepContext, coupon):
    ctx.driver.open(ctx.url("/coupon.html"))
    ctx.driver.type("coupon-select", coupon)
    ctx.driver.click("coupon-apply")
    # 적용 성공 시 결제 화면 이동
    wait_until(lambda: "원" in ctx.driver.text_of("checkout-total"))


@step('"{target}" 버튼을 누르면')
def click(ctx: StepContext, target):
    ctx.driver.click(resolve(target))


@step('결제 금액은 "{expected}"원이다')
def order_total_is(ctx: StepContext, expected):
    # 가장 최근 주문 금액 (주문 내역 화면)
    text = ctx.driver.text_of("xpath=(//*[starts-with(@data-testid,'order-total-')])[last()]")
    actual = amount(text)
    assert actual == amount(expected), f"결제 금액 {actual} != 기대 {expected}"
