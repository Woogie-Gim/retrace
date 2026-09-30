"""교란 스텝 : Driver 인터페이스 호출만 사용"""
from ..scenario.registry import StepContext, step
from .shop import resolve


@step('"{target}" 버튼(을|를) 빠르게 {n:d}회 누르면')
def rapid_click(ctx: StepContext, target, n):
    ctx.driver.click(resolve(target), times=n)


@step("브라우저 뒤로가기(을|를) 하면")
def back(ctx: StepContext):
    ctx.driver.back()


@step("페이지(을|를) 새로고침하면")
def refresh(ctx: StepContext):
    ctx.driver.refresh()


@step('네트워크(을|를) "{profile}" 상태로 바꾸면')
def set_network(ctx: StepContext, profile):
    ctx.driver.set_network(profile)


@step("창 크기(을|를) {w:d}x{h:d}로 바꾸면")
def resize(ctx: StepContext, w, h):
    ctx.driver.resize(w, h)


@step('"{field}"에 "{value}"(을|를) 입력하면')
def type_value(ctx: StepContext, field, value):
    ctx.driver.type(resolve(field), value)
