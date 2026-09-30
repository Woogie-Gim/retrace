"""pytest-bdd 어댑터 : 레지스트리 스텝을 pytest-bdd 스텝으로 등록"""
import inspect

from pytest_bdd import parsers, step as bdd_step

from .registry import StepDef, StepRegistry, registry as default_registry


def _wrap(d: StepDef):
    def wrapper(ctx, **kwargs):
        return d.func(ctx, **kwargs)

    # pytest-bdd는 시그니처로 주입 인자 결정 → (ctx, 패턴 필드들)
    P = inspect.Parameter
    wrapper.__signature__ = inspect.Signature(
        [P("ctx", P.POSITIONAL_OR_KEYWORD)] + [P(f, P.POSITIONAL_OR_KEYWORD) for f in d.fields]
    )
    wrapper.__name__ = d.func.__name__
    return wrapper


def register_pytest_bdd(registry: StepRegistry | None = None, stacklevel: int = 1) -> None:
    """호출한 모듈(conftest 등)에 스텝 픽스처 주입. ctx 픽스처는 호출 측에서 제공"""
    for d in (registry or default_registry).defs:
        # 프레임 : pytest-bdd decorator → 이 함수 → 호출 모듈
        bdd_step(parsers.parse(d.pattern), stacklevel=stacklevel + 1)(_wrap(d))
