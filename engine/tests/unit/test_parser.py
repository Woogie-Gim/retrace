from retrace import config
from retrace.scenario import parse_feature, parse_feature_file

SEED = config.ROOT_DIR / "features" / "seeds" / "gold_coupon.feature"


def test_seed_feature():
    f = parse_feature_file(SEED)
    assert f.name == "골드 회원 쿠폰 결제"
    assert f.tags == ["@oracle-api", "@oracle-console"]
    assert "증상" in f.description
    sc = f.scenarios[0]
    assert [s.keyword for s in sc.steps] == ["Given", "When", "And", "And", "Then"]
    assert [s.background for s in sc.steps] == [True, False, False, False, False]
    assert sc.steps[1].text == '"상품-1"을 장바구니에 담으면'


def test_background_merged_per_scenario():
    f = parse_feature(
        "Feature: F\n"
        "  Background:\n    Given a\n"
        "  @t\n  Scenario: S1\n    When b\n"
        "  Scenario: S2\n    When c\n"
    )
    assert [[s.text for s in sc.steps] for sc in f.scenarios] == [["a", "b"], ["a", "c"]]
    assert f.scenarios[0].tags == ["@t"]
