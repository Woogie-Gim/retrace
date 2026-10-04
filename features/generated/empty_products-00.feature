# Retrace 생성 최소 재현 시나리오
# 원본 : reports/minimize-20260930-150332/empty_products-00/minimize.json
@oracle-console @oracle-network
Feature: 상품 목록 빈 화면
  증상: 가끔 상품 목록이 아무것도 안 뜸
  재현율: 100% (확정) / 원인 계층: FE

  Background:
    Given "일반" 등급 회원으로 로그인하면

  Scenario: 상품 목록 확인 (최소 재현)
    # 교란(network)
    When 네트워크를 "slow-3g" 상태로 바꾸면
    And "상품 목록" 화면을 열면
    Then 상품 목록에 "상품-1"이 보인다
