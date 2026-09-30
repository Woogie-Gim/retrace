@oracle-console @oracle-network
Feature: 상품 목록 빈 화면
  증상: 가끔 상품 목록이 아무것도 안 뜸

  Background:
    Given "일반" 등급 회원으로 로그인하면

  Scenario: 상품 목록 확인
    When "상품 목록" 화면을 열면
    Then 상품 목록에 "상품-1"이 보인다
