# Retrace 생성 최소 재현 시나리오
# 원본 : reports/minimize-20260930-144544/double_order-00/minimize.json
@oracle-api @oracle-network
Feature: 결제 중복 주문
  증상: 결제 한 번에 주문이 두 건 생기는 경우가 있음
  재현율: 100% (확정) / 원인 계층: BE

  Background:
    Given "일반" 등급 회원으로 로그인하면

  Scenario: 결제 후 주문 내역 확인 (최소 재현)
    When "상품-1"을 장바구니에 담으면
    And "결제" 화면을 열면
    And "결제" 버튼을 누르면
    # 교란(rapid_click)
    And "결제" 버튼을 빠르게 3회 누르면
    Then 주문 내역은 "1"건이다
