"""엔진이 생성한 최소 재현 시나리오 회귀 테스트 (BUG_MODE=on 실패 / off 통과)"""
from pytest_bdd import scenarios

from retrace import config

GENERATED = config.ROOT_DIR / "features" / "generated"

# 생성 feature 없으면 수집 생략
if any(GENERATED.glob("*.feature")):
    scenarios(str(GENERATED))
