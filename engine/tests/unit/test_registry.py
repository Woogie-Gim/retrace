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


def test_josa_both_allowed():
    cases = {
        '"상품-1"을 장바구니에 담으면': {"product": "상품-1"},
        '"상품-1"를 장바구니에 담으면': {"product": "상품-1"},
        '"10% 쿠폰"를 적용하면': {"coupon": "10% 쿠폰"},
        '"결제" 버튼을 빠르게 3회 누르면': {"target": "결제", "n": 3},
        '"결제" 버튼를 빠르게 3회 누르면': {"target": "결제", "n": 3},
        '브라우저 뒤로가기를 하면': {},
        '페이지를 새로고침하면': {},
        '네트워크를 "slow-3g" 상태로 바꾸면': {"profile": "slow-3g"},
        '창 크기를 375x667로 바꾸면': {"w": 375, "h": 667},
        '"수량"에 "0"을 입력하면': {"field": "수량", "value": "0"},
        '"수량"에 "-1"를 입력하면': {"field": "수량", "value": "-1"},
        '상품 목록에 "상품-1"이 보인다': {"product": "상품-1"},
        '상품 목록에 "상품-2"가 보인다': {"product": "상품-2"},
    }
    for text, kw in cases.items():
        assert registry.match(text)[1] == kw, text


def test_expand_registers_variants_with_flag():
    r = StepRegistry()
    defs = r.add('"{a}"(을|를) 적용하면', lambda ctx, a: None, idempotent=True)
    assert [d.pattern for d in defs] == ['"{a}"을 적용하면', '"{a}"를 적용하면']
    assert all(d.idempotent for d in defs)
