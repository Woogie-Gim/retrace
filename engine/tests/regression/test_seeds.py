"""시드 시나리오를 공용 스텝 정의로 pytest-bdd 실행"""
from pytest_bdd import scenarios

from retrace import config

scenarios(str(config.ROOT_DIR / "features" / "seeds"))
