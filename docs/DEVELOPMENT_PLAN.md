# Retrace 개발 계획서

> 증상만 알려진 간헐 이슈의 **최소 재현 스텝을 자동으로 찾아내는** 웹 QA 도구
> Claude Code로 Phase 단위 개발을 진행하기 위한 기준 문서 (`docs/DEVELOPMENT_PLAN.md` 위치)

---

## 0. 개요

### 0-1. 목표

| 구분 | 내용 |
|---|---|
| 입력 | 시드 시나리오(`.feature`) + 증상 설명 + 오라클 태그 |
| 처리 | 교란 탐색 → 오라클 판정 → 최소화 → 재현율 검증 |
| 출력 | 최소 재현 스텝(`.feature`) + 재현율 + FE/BE 원인 계층 + 증거 로그 |
| 핵심 메시지 | 찾아낸 재현 스텝이 곧 실행 가능한 회귀 테스트 |

### 0-2. 기술 스택

| 영역 | 스택 |
|---|---|
| 엔진 | Python 3.11 / Selenium 4 / gherkin-official / parse / requests |
| 회귀 테스트 | pytest / pytest-bdd |
| 데모 타깃 | FastAPI + Vanilla HTML/JS (버그 심은 쇼핑몰) |
| 엔진 서버 | FastAPI + WebSocket (실시간 진행 스트림) |
| 프론트엔드 | Electron + Vanilla JS 또는 Vite |
| LLM (선택) | Claude API |
| 빌드 | PyInstaller (엔진) + electron-builder (앱) |
| 배포 | GitHub Releases |

### 0-3. 전체 일정

| Phase | 내용 | 예상 | 태그 |
|---|---|---|---|
| 0 | 환경 세팅 + 저장소 생성 | 0.5일 | v0.0.1 |
| 1 | 버그 심은 데모 쇼핑몰 | 0.5일 | v0.1.0 |
| 2 | 엔진 코어 (드라이버 + BDD 실행기) | 1일 | v0.2.0 |
| 3 | Explorer + Oracle | 1일 | v0.3.0 |
| 4 | Minimizer + Verifier | 0.5일 | v0.4.0 |
| 5 | Reporter + 회귀 테스트 연동 | 0.5일 | v0.5.0 |
| 6 | 프론트엔드 대시보드 | 1.5일 | v0.6.0 |
| 7 | LLM 보조 (선택) | 0.5일 | v0.7.0 |
| 8 | 빌드 + 릴리스 | 1일 | v1.0.0 |
| 9 | README + 시연 자료 | 0.5일 | v1.0.1 |

일정이 밀리면 Phase 7을 가장 먼저 제외.

### 0-4. 폴더 구조

```
retrace/
├── engine/
│   ├── retrace/
│   │   ├── driver/          # Driver 인터페이스 + SeleniumDriver
│   │   ├── scenario/        # feature 파싱 + 스텝 레지스트리
│   │   ├── steps/           # 공용 스텝 정의 (엔진·pytest-bdd 공유)
│   │   ├── explorer/        # 교란 카탈로그 + 탐색기
│   │   ├── oracle/          # console / network / dom / api
│   │   ├── minimizer/       # ddmin
│   │   ├── verifier/        # 재현율 측정
│   │   ├── reporter/        # feature / md / html 출력
│   │   ├── llm/             # 증상 해석 (선택)
│   │   └── server/          # FastAPI + WebSocket
│   ├── tests/
│   │   ├── unit/
│   │   └── regression/      # 생성된 feature 실행
│   └── requirements.txt
├── demo-shop/               # 버그 심은 타깃 웹앱
├── features/
│   ├── seeds/               # 사람이 작성한 시드 시나리오
│   └── generated/           # 엔진이 만든 최소 재현 시나리오
├── app/                     # Electron 프론트엔드
├── reports/                 # 실행 결과 (git 제외)
├── docs/
│   └── DEVELOPMENT_PLAN.md
├── .env.example
├── .gitignore
└── README.md
```

### 0-5. Git 규칙

- 브랜치 : `main` + Phase별 `feat/phase-N-이름`
- 커밋 : `feat` / `fix` / `refactor` / `test` / `docs` / `chore` 접두어 + 한국어 요약
- 병합 : Phase 완료 시 `--no-ff` 병합 후 태그 푸시
- 금지 : `.env` / `reports/` / 빌드 산출물 커밋

Phase 공통 흐름

```bash
git checkout -b feat/phase-N-이름
# 작업 단위마다 커밋
git add .
git commit -m "feat(scope): 작업 요약"
# Phase 완료 기준 통과 후
git checkout main
git merge --no-ff feat/phase-N-이름
git tag vX.Y.Z
git push origin main --tags
```

### 0-6. Claude Code 사용 규칙

- 지시 예시 : `docs/DEVELOPMENT_PLAN.md의 Phase 3만 진행. 완료 기준 확인 후 멈추고 커밋 메시지 제안`
- 한 번에 한 Phase만 진행
- Phase 종료 시 완료 기준 체크리스트 직접 확인 후 병합

---

## Phase 0 — 환경 세팅 + 저장소 생성

### 작업
1. GitHub에서 `retrace` 빈 저장소 생성 (README·.gitignore 체크 해제)
2. 로컬 폴더 구조 생성 + 이 문서를 `docs/`에 배치
3. `engine/` 가상환경 생성 (트레이딩 프로젝트와 별도 venv)
4. `.gitignore` / `.env.example` / `requirements.txt` 작성

```bash
mkdir retrace && cd retrace
git init -b main
python -m venv engine/.venv
source engine/.venv/Scripts/activate   # Git Bash 기준
pip install selenium gherkin-official parse requests fastapi uvicorn pytest pytest-bdd python-dotenv
pip freeze > engine/requirements.txt
```

`.gitignore`

```
# python
__pycache__/
*.pyc
.venv/
# node
node_modules/
# build
dist/
build/
*.spec
release/
# runtime
reports/
.env
```

`.env.example`

```
DEMO_SHOP_PORT=5100
ENGINE_PORT=5200
ANTHROPIC_API_KEY=
LLM_MODEL=
```

포트는 트레이딩 프로젝트 Electron 개발 서버와 겹치지 않게 5100번대로 고정.

### 완료 기준
- [ ] venv 활성화 후 `python -c "import selenium"` 성공
- [ ] 원격 저장소 연결 및 첫 푸시 완료

### Git
```bash
git add .
git commit -m "chore: 프로젝트 초기 구조 및 개발 계획서 추가"
git remote add origin https://github.com/Woogie-Gim/retrace.git
git push -u origin main
git tag v0.0.1 && git push origin --tags
```

---

## Phase 1 — 버그 심은 데모 쇼핑몰 (`demo-shop/`)

실서비스는 재현 보장이 불가능하므로 시연용 타깃을 직접 제작.

### 화면과 API

| 화면 | API |
|---|---|
| 로그인 (회원 등급 선택: 일반/실버/골드) | `POST /api/login` |
| 상품 목록 | `GET /api/products` |
| 장바구니 | `GET·POST /api/cart` |
| 쿠폰 적용 + 결제 | `POST /api/coupons/apply` / `POST /api/orders` |
| 주문 내역 | `GET /api/orders` |
| 상태 초기화 (테스트용) | `POST /api/reset` |

### 심어둘 버그

| ID | 증상 | 트리거 | 원인 계층 | 발생 방식 |
|---|---|---|---|---|
| BUG-01 | 주문이 2건 생성됨 | 결제 버튼 연타 | BE (멱등성 없음) | 처리 지연 중 재요청 시 100% |
| BUG-02 | 골드 쿠폰 할인이 이중 적용됨 | 쿠폰 적용 → 뒤로가기 → 재적용 | BE (쿠폰 사용 플래그 미갱신) | 확률 50% |
| BUG-03 | 상품 목록이 빈 화면 | 느린 네트워크 | FE (로딩·타임아웃 처리 누락) | 응답 2초 초과 시 |
| BUG-04 | 화면 장바구니 수량 3 / 서버 2 | 수량 버튼 빠른 연속 클릭 | FE (낙관적 업데이트 롤백 누락) | 확률 30% |

### 구현 규칙
- 모든 조작 요소에 `data-testid` 부여 (로케이터 안정성)
- 환경변수 `BUG_MODE=on|off` : off면 버그 전부 수정된 동작 → 회귀 테스트 통과 확인용
- 환경변수 `BUG_SEED` : 확률 버그 난수 시드 고정 (시연 재현성)

### 완료 기준
- [ ] 수동으로 BUG-01~04 모두 재현 확인
- [ ] `BUG_MODE=off`에서 4종 모두 미발생

### Git
```bash
git checkout -b feat/phase-1-demo-shop
git commit -m "feat(demo-shop): 쇼핑몰 화면 및 API 구현"
git commit -m "feat(demo-shop): 버그 4종 및 BUG_MODE 토글 추가"
# 병합 후 태그 v0.1.0
```

---

## Phase 2 — 엔진 코어: 드라이버 + BDD 실행기

### 2-1. Driver 인터페이스
게임 확장 대비 핵심 설계. Explorer 이후 단계는 이 인터페이스만 사용.

```python
class Driver(ABC):
    # 공통 조작
    @abstractmethod
    def open(self, url: str) -> None: ...
    @abstractmethod
    def click(self, target: str, times: int = 1, interval_ms: int = 0) -> None: ...
    @abstractmethod
    def type(self, target: str, value: str) -> None: ...
    @abstractmethod
    def text_of(self, target: str) -> str: ...
    # 교란 조작
    @abstractmethod
    def back(self) -> None: ...
    @abstractmethod
    def refresh(self) -> None: ...
    @abstractmethod
    def set_network(self, profile: str) -> None: ...
    @abstractmethod
    def resize(self, w: int, h: int) -> None: ...
    # 증거 수집
    @abstractmethod
    def screenshot(self, path: str) -> None: ...
    @abstractmethod
    def console_logs(self) -> list[dict]: ...
    @abstractmethod
    def network_logs(self) -> list[dict]: ...
```

### 2-2. SeleniumDriver
- `goog:loggingPrefs`에 `browser`·`performance` 활성화 → 콘솔·네트워크 로그 수집
- 네트워크 교란은 `execute_cdp_cmd("Network.emulateNetworkConditions", ...)` 사용
- headless 기본 + 드라이버 재사용 (실행마다 `/api/reset`으로 상태만 초기화)
- 로케이터는 `data-testid` 우선

### 2-3. 스텝 레지스트리
- 스텝 정의는 `steps/`에 한 번만 작성
- 엔진 실행기와 pytest-bdd 양쪽에 어댑터로 등록 (Phase 2에서 동작 검증 필수)

```python
@step('"{grade}" 등급 회원으로 로그인하면')
def login(ctx, grade):
    # 등급별 테스트 계정 로그인
    ...

@step('"{target}" 버튼을 누르면')
def click(ctx, target):
    ctx.driver.click(target)
```

### 2-4. 실행기
- `gherkin-official`로 `.feature` 파싱 → `Step` 리스트
- 스텝 순차 실행 → `RunResult(steps, failed_at, logs, screenshots)` 반환
- Given/When/Then 키워드는 영문 유지 + 문장은 한국어

시드 시나리오 예시 (`features/seeds/gold_coupon.feature`)

```gherkin
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
```

### 완료 기준
- [ ] 시드 시나리오 1개가 엔진 실행기로 끝까지 실행됨
- [ ] 같은 스텝 정의로 pytest-bdd 실행 성공
- [ ] 콘솔·네트워크 로그 JSON 저장 확인

### Git
```bash
git checkout -b feat/phase-2-engine-core
git commit -m "feat(driver): Driver 인터페이스 및 SeleniumDriver 구현"
git commit -m "feat(scenario): feature 파서 및 스텝 레지스트리 구현"
git commit -m "test: pytest-bdd 어댑터 동작 검증"
# 병합 후 태그 v0.2.0
```

---

## Phase 3 — Explorer + Oracle

### 3-1. 교란 카탈로그

| 교란 | Gherkin 문장 | 노리는 결함 유형 |
|---|---|---|
| 연타 | `"{target}" 버튼을 빠르게 {n}회 누르면` | 중복 요청 / 레이스 |
| 뒤로가기 | `브라우저 뒤로가기를 하면` | 상태 꼬임 / 재사용 |
| 새로고침 | `페이지를 새로고침하면` | 세션·캐시 불일치 |
| 네트워크 | `네트워크를 "{profile}" 상태로 바꾸면` | 로딩·타임아웃 처리 |
| 창 크기 | `창 크기를 {w}x{h}로 바꾸면` | 반응형 레이아웃 |
| 경계값 | `"{field}"에 "{value}"를 입력하면` | 입력 검증 |

네트워크 프로필 : `fast` / `slow-3g` / `offline`

### 3-2. 탐색 전략
- 후보 = 삽입 위치 × 교란 종류 (Background 스텝 사이 제외)
- 우선순위 : 상태 변경 스텝(결제·적용·담기) 직후 삽입 우선
- 간헐 이슈 대응 : 후보마다 k회(기본 3) 반복 실행 후 1회라도 적중하면 hit
- 예산 : `max_runs`(기본 60) 초과 시 종료
- 1차 hit 발견 즉시 Phase 4로 넘김 (옵션으로 전체 탐색 후 상위 N개 수집)

### 3-3. Oracle

```python
@dataclass
class Verdict:
    hit: bool
    kind: str      # console / network / dom / api
    detail: str
```

| Oracle | 판정 기준 | 활성화 |
|---|---|---|
| DomOracle | Then 스텝 실패 | 항상 |
| ConsoleOracle | SEVERE 레벨 콘솔 에러 | `@oracle-console` |
| NetworkOracle | 4xx·5xx 응답 | `@oracle-network` |
| ApiOracle | 화면 값과 API 값 비교 | `@oracle-api` |

ApiOracle은 `requests`로 `/api/orders`·`/api/cart`를 조회해 화면 값과 대조. 결과는 Phase 5 원인 계층 분류에 사용.

### 완료 기준
- [ ] BUG-01~04 각각 시드 시나리오만으로 탐색기가 hit 발견
- [ ] `BUG_MODE=off`에서 false positive 0건

### Git
```bash
git checkout -b feat/phase-3-explorer-oracle
git commit -m "feat(explorer): 교란 카탈로그 및 우선순위 탐색 구현"
git commit -m "feat(oracle): console/network/dom/api 오라클 구현"
# 병합 후 태그 v0.3.0
```

---

## Phase 4 — Minimizer + Verifier

### 4-1. Minimizer (Delta Debugging)
- hit 시퀀스에서 불필요 스텝을 제거해 최소 재현 스텝 도출
- 판정 함수 : 후보 시퀀스를 k회 실행해 1회라도 hit면 유지
- Background 스텝은 제거 대상에서 제외

```
ddmin(steps, n=2):
  steps를 n등분
  각 조각만 남겨 hit → 그 조각으로 재귀 (n=2)
  각 조각을 빼고 hit → 여집합으로 재귀 (n=max(n-1, 2))
  둘 다 실패 → n을 2배 (최대 len(steps))
  n == len(steps)에서 실패 → 현재 steps 반환
```

### 4-2. Verifier
- 최소 스텝 N회(기본 10) 반복 실행 → 재현율 산출
- 등급 : 100% `확정` / 30% 이상 `간헐` / 30% 미만 `희귀` / 0% `미재현` / 유효 실행 0회 `판정불가`
- 선택 검증 : `BUG_MODE=off`에서 0% 확인 → 수정 검증 시나리오로 활용

### 완료 기준
- [ ] BUG-02 기준 hit 시퀀스 대비 스텝 수 감소 확인
- [ ] 재현율과 등급이 결과 객체에 기록됨

### Git
```bash
git checkout -b feat/phase-4-minimizer-verifier
git commit -m "feat(minimizer): ddmin 기반 최소 재현 스텝 도출"
git commit -m "feat(verifier): 반복 실행 재현율 측정 및 등급 분류"
# 병합 후 태그 v0.4.0
```

---

## Phase 5 — Reporter + 회귀 테스트 연동

### 5-1. 출력물 (`reports/<run_id>/`)

| 파일 | 내용 |
|---|---|
| `repro.feature` | 최소 재현 시나리오 (`features/generated/`에도 복사) |
| `report.md` | Jira 형식 버그 리포트 |
| `report.json` | 프론트엔드 표시용 원본 데이터 |
| `evidence/` | 스텝별 스크린샷 + 콘솔·네트워크 로그 |

### 5-2. 원인 계층 분류

| 조건 | 분류 |
|---|---|
| API 값 이상 또는 5xx | BE |
| API 정상 + 화면 값 불일치 | FE |
| JS 콘솔 에러만 존재 | FE |
| 판단 불가 | 미분류 |

### 5-3. report.md 템플릿

```markdown
## [간헐 70%] 골드 회원 쿠폰 할인 이중 적용

- 환경 : Chrome 버전 / 창 크기 / 네트워크 프로필
- 원인 계층 : BE (API 결제 금액 불일치)
- 사전 조건 : 골드 등급 회원 로그인

### 재현 스텝
1. 상품-1을 장바구니에 담음
2. 10% 쿠폰 적용
3. 브라우저 뒤로가기   ← 탐색으로 찾은 교란
4. 10% 쿠폰 재적용
5. 결제

### 기대 결과
결제 금액 27000원

### 실제 결과
결제 금액 24300원 (API 주문 금액 동일)

### 증거
스크린샷 / 콘솔 로그 / 네트워크 로그 링크
```

### 5-4. 회귀 테스트
- `pytest engine/tests/regression`으로 `features/generated/*.feature` 일괄 실행
- `BUG_MODE=on` 실패 / `BUG_MODE=off` 통과 확인

### 완료 기준
- [ ] BUG-01~04 리포트 4건 생성
- [ ] 생성된 feature가 pytest-bdd로 그대로 실행됨

### Git
```bash
git checkout -b feat/phase-5-reporter
git commit -m "feat(reporter): feature/md/json 리포트 생성"
git commit -m "feat(reporter): FE/BE 원인 계층 자동 분류"
git commit -m "test: 생성 시나리오 회귀 테스트 연동"
# 병합 후 태그 v0.5.0
```

---

## Phase 6 — 프론트엔드 대시보드 (`app/`)

### 6-1. 엔진 서버 API

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/health` | 엔진 기동 확인 |
| GET | `/scenarios` | 시드 목록 |
| POST | `/runs` | 탐색 실행 시작 |
| WS | `/runs/{id}/stream` | 실시간 진행 이벤트 |
| GET | `/reports` · `/reports/{id}` | 결과 조회 |

스트림 이벤트 : `candidate_start` / `hit` / `minimize_step` / `verify_progress` / `done`

### 6-2. 화면 구성
1. **시나리오** : 시드 목록 + feature 미리보기 + 오라클 태그 토글
2. **실행** : 진행률 바 / 시도 후보 수 / hit 수 / 실시간 로그 콘솔
3. **리포트** : 스텝 타임라인 (교란 스텝 강조) + 스텝별 스크린샷 + 재현율 게이지 + FE/BE 뱃지 + feature 복사 버튼
4. **히스토리** : 과거 실행 목록 + 재현율 추이

### 6-3. 디자인 가이드
- 톤 : 다크 계열 QA 콘솔 느낌
- 폰트 : 본문 Pretendard / 로그·스텝 JetBrains Mono
- 색상 토큰 : `--bg` `--surface` `--text` `--accent` + 상태색 (`확정` 빨강 / `간헐` 주황 / `희귀` 회색 / `FE` 파랑 / `BE` 보라)
- 교란 스텝은 타임라인에서 accent 색 + 아이콘으로 구분
- 빈 상태·로딩·에러 화면 모두 디자인 (QA 도구답게 예외 화면 누락 금지)

### 6-4. Electron 구조
- main 프로세스가 엔진 실행 (개발 : `python -m retrace.server` / 배포 : `engine.exe`)
- `/health` 폴링으로 기동 확인 후 창 표시
- 앱 종료 시 엔진 프로세스 확실히 종료 (좀비 프로세스 방지)

### 완료 기준
- [ ] 앱에서 시드 선택 → 실행 → 리포트 확인까지 끊김 없이 동작
- [ ] 엔진 미기동·실행 실패 시 에러 화면 표시

### Git
```bash
git checkout -b feat/phase-6-frontend
git commit -m "feat(server): 실행 API 및 WebSocket 스트림 구현"
git commit -m "feat(app): Electron 셸 및 엔진 프로세스 관리"
git commit -m "feat(app): 시나리오·실행·리포트·히스토리 화면 구현"
git commit -m "style(app): 디자인 토큰 및 상태 뱃지 적용"
# 병합 후 태그 v0.6.0
```

---

## Phase 7 — LLM 보조 (선택)

### 역할
- 증상 설명 텍스트 → 교란 우선순위 + 추천 오라클 태그 JSON 반환
- Explorer 후보 정렬에만 반영하고 실행 자체는 규칙 기반 유지 (결과 재현성 확보)

```json
{
  "perturbations": ["back", "rapid_click"],
  "oracles": ["api"],
  "reason": "금액 이상 증상이라 상태 재사용 계열 우선"
}
```

### 규칙
- API 키 없으면 기본 우선순위로 자동 폴백
- 리포트에 LLM 추천 사용 여부 표기
- 비교 지표 : LLM 사용 전후 첫 hit까지 시도 횟수

### 완료 기준
- [ ] 키 유무 양쪽 모두 정상 동작
- [ ] 첫 hit까지 시도 횟수 비교표 확보

### Git
```bash
git checkout -b feat/phase-7-llm
git commit -m "feat(llm): 증상 기반 교란 우선순위 추천"
# 병합 후 태그 v0.7.0
```

---

## Phase 8 — 빌드 + 릴리스

### 8-1. 엔진 빌드 (PyInstaller)

```bash
cd engine
pyinstaller -n engine --onedir --collect-all selenium --collect-all gherkin retrace/server/__main__.py
```

- Selenium Manager 바이너리 포함 여부 확인 (`--collect-all selenium`)
- 데모 쇼핑몰도 `demo-shop.exe`로 별도 빌드해 앱 하나로 시연 가능하게 구성

### 8-2. 앱 빌드 (electron-builder)
- `extraResources`로 `engine/dist/engine` + `demo-shop.exe` 포함
- 타깃 : Windows NSIS 설치본 + portable zip
- 앱 이름 `Retrace` / 버전 `1.0.0`

### 8-3. 클린 환경 점검
- [ ] Python 미설치 PC에서 실행 확인
- [ ] 크롬만 설치된 상태에서 첫 실행 시 드라이버 자동 확보 확인 (인터넷 필요)
- [ ] 포트 점유 시 에러 메시지 표시
- [ ] 앱 종료 후 작업 관리자에 엔진·크롬 프로세스 잔존 없음

### 8-4. GitHub Release

```bash
git checkout -b chore/phase-8-build
git commit -m "chore(build): PyInstaller 및 electron-builder 설정"
git checkout main
git merge --no-ff chore/phase-8-build
git tag v1.0.0
git push origin main --tags
gh release create v1.0.0 release/*.exe release/*.zip --title "Retrace v1.0.0" --notes-file docs/RELEASE_NOTES.md
```

`gh` 미설치 시 GitHub 웹 Releases 화면에서 태그 선택 후 파일 업로드.

---

## Phase 9 — README + 시연 자료

### 작업
- README의 `측정 후 기입` 항목을 실제 수치로 교체
- 시연 GIF 3종 : 탐색 실행 / 리포트 확인 / 회귀 테스트 실행 (ScreenToGif 등)
- 버그 4종 결과표 작성 : 시드 스텝 수 → 최소 스텝 수 / 첫 hit 시도 횟수 / 재현율 / 원인 계층
- 이력서·자소서용 한 줄 요약 확정

### 이력서 문장 초안 (수치는 측정 후 기입)
- 증상만 알려진 간헐 결함의 최소 재현 스텝을 자동 탐색하는 Selenium 기반 도구 개발 (재현율 ○○% / 스텝 ○○% 축소)
- 탐색 결과를 BDD 시나리오로 출력해 재현 스텝을 회귀 테스트로 즉시 전환
- UI·API 교차 검증으로 결함 원인 계층(FE/BE) 자동 분류

### Git
```bash
git checkout -b docs/phase-9-readme
git commit -m "docs: README 결과표 및 시연 GIF 추가"
# 병합 후 태그 v1.0.1
```

---

## 부록 — 게임 확장 메모 (3년차 계획)

- `GameDriver(Driver)` 구현 : ADB 입력 + VLM 화면 판정 (기존 VLM 자동화 코드 재사용)
- 게임 교란 후보 : 화면 전환 중 터치 연타 / 앱 백그라운드 전환 / 네트워크 단절 / 기기 회전
- Explorer·Minimizer·Verifier·Reporter는 수정 없이 재사용하는 것이 설계 목표
