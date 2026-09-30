@oracle-api @oracle-console
Feature: 골드 회원 쿠폰 결제
  증상: 골드 회원 결제 금액이 가끔 너무 낮게 찍힘

  Background:
    Given "골드" 등급 회원으로 로그인하면

  Scenario: 쿠폰 적용 후 결제
    When "상품-1"을 장바구니에 담으면
    And "10% 쿠폰"을 적용하면
    And "결제" 버튼을 누르면
    Then 결제 금액은 "27000"원이다
