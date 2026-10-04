# Retrace 생성 최소 재현 시나리오
# 원본 : reports/minimize-20260930-144544/cart_qty-00/minimize.json
@oracle-api @oracle-network
Feature: 장바구니 수량 불일치
  증상: 장바구니 화면 수량과 실제 주문 수량이 다른 경우가 있음
  재현율: 90% (간헐) / 원인 계층: FE

  Background:
    Given "일반" 등급 회원으로 로그인하면

  Scenario: 장바구니 수량 증가 (최소 재현)
    When "상품-1"을 장바구니에 담으면
    And "장바구니" 화면을 열면
    And "상품-1 수량 증가" 버튼을 누르면
    # 교란(rapid_click)
    And "상품-1 수량 증가" 버튼을 빠르게 3회 누르면
    Then 장바구니 화면 수량이 서버와 일치한다
