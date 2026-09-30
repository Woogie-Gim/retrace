import pytest

from retrace import steps  # noqa: F401
from retrace.scenario.registry import StepNotFound, StepRegistry, registry


def test_shop_steps_match():
    cases = {
        '"골드" 등급 회원으로 로그인하면': {"grade": "골드"},
        '"상품-1"을 장바구니에 담으면': {"product": "상품-1"},
        '"10% 쿠폰"을 적용하면': {"coupon": "10% 쿠폰"},
        '"결제" 버튼을 누르면': {"target": "결제"},
        '결제 금액은 "27000"원이다': {"expected": "27000"},
    }
    for text, kw in cases.items():
        assert registry.match(text)[1] == kw


def test_run_passes_ctx_and_args():
    r = StepRegistry()
    calls = []
    r.step('"{a}" 누르면')(lambda ctx, a: calls.append((ctx, a)))
    r.run("CTX", '"x" 누르면')
    assert calls == [("CTX", "x")]


def test_unknown_and_ambiguous():
    r = StepRegistry()
    r.step('"{a}" 누르면')(lambda ctx, a: None)
    with pytest.raises(StepNotFound):
        r.match("없는 스텝")
    r.step('"{b}" {c}면')(lambda ctx, b, c: None)
    with pytest.raises(StepNotFound, match="모호"):
        r.match('"x" 누르면')
