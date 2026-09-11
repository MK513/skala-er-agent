# ER Finder · skala-er-agent

응급실 탐색 프로젝트의 팀 저장소입니다. **1~5번 모듈의 구현이 main에 병합되었지만, 모듈 간 인터페이스와 데이터 처리 오류로 실제 서비스 연결은 막혀 있습니다.** 6번의 로컬 작업에는 Streamlit 화면과 자동 검증 도구가 있습니다.

## 개발 목표와 현재 연결 상태

최종 실행 기준은 **실제 OpenAI·카카오·E-Gen API를 사용하는 서비스**입니다. 현재 합성 화면은 UI 회귀 검증용이며 실제 모드 완성을 대신하지 않습니다. 실제 모드 오류나 키 누락 시 합성 결과로 자동 대체하지 않습니다.

2026-09-11 기준 `main`의 `e97341a`까지 로컬에 반영했습니다. 메모리·검색·에이전트·가드레일·의료 API의 PR #1~#5가 병합되었습니다. 최신 오프라인 검증은 **174개 통과, 수집 오류 6건으로 전체 FAIL**입니다. 수정 위치와 재현 근거는 [최신 통합 검토](docs/review-2026-09-11.md)에 정리했습니다.

## 바로 실행

Python 3.11 이상이 필요합니다. Streamlit 화면 자체는 키 없이 실행됩니다. 실제 조회에는 해당 API 키가 필요합니다.

```bash
cd skala-er-agent
uv sync --frozen --extra dev
uv run --frozen streamlit run streamlit_app.py
```

uv 없이 설치할 수도 있습니다. 이 경우 uv.lock의 고정 버전을 사용하지 않습니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
streamlit run streamlit_app.py
```

설치 후 `er-finder` 또는 `python -m er_finder`도 같은 웹 화면을 실행합니다. 대화형 CLI와 실제 runner 연결은 완료되지 않았습니다. 기본 바인딩은 localhost입니다.

## 현재 화면에서 할 수 있는 것

- 고정 합성 시나리오 6종: 후보 3곳, 위치 재질문, 후보 없음, 119 안내, 갱신 지연, 서비스 오류.
- 가상 후보 카드: 거리, 병상, 주소, 전화번호 확인 불가, 갱신 시각과 데이터 상태.
- 병원 선택 → 승인 전 저장 0건 → 승인 후 방문 계획 저장. 거절하면 저장하지 않음.
- 브라우저별 대화·프로필 분리. 새 대화는 프로필 유지, 기록 전체 삭제는 프로필까지 삭제.
- 기본 주소 저장 동의·철회. 시나리오·이동수단 변경 시 기존 후보와 승인 대기 취소.
- 실제 API 모드가 기본입니다. 연결 확인 후 사용할 대화·승인 어댑터와 키 설정 상태 화면을 제공합니다.
- 의료 API 조회 탭은 좌표와 반경으로 기존 E-Gen 주변 기관 목록 함수를 직접 호출합니다. 조회 버튼에서만 호출하며 합성 결과로 대체하지 않습니다.
- 현재 runner의 import·provider 계약 오류로 전체 추천은 연결 대기입니다. 키 설정만으로 해결되지는 않습니다.

화면 검토용 데모에서는 입력 내용으로 증상을 분류하거나 위치를 해석하지 않고 고정 예시를 재생합니다. 합성 기관의 전화번호는 만들지 않습니다. 이 데모는 실제 응급실 안내에 사용할 수 없습니다.

## 검증

```bash
uv run --frozen python scripts/verify.py
uv run --frozen pytest tests/integration/test_streamlit.py
uv run --frozen ruff check .
```

`verify.py`는 live 표시 테스트를 제외하고, 테스트 프로세스의 Python 소켓 네트워크 호출을 차단합니다. 수집 오류가 있어도 실행 가능한 테스트 결과를 기록하되, 전체 결과는 실패로 유지합니다. 로컬 테스트 결과와 전체 서비스 연결 상태를 구분합니다.

생성물: `verification-results/report.json`, `junit.xml`, `pytest.log`. 이 디렉터리는 git에서 제외됩니다. CI도 같은 검증을 실행하고 결과를 아티팩트로 남기도록 구성했습니다. 브랜치 push 시 원격 CI가 실행됩니다. 기존 백엔드 수집 오류가 남아 전체 검증은 실패할 수 있습니다.

```bash
uv run --frozen python scripts/verify.py --require-integration
```

현재 테스트 수집 오류로 위 명령은 종료 코드 1을 반환합니다. 로컬 테스트가 모두 통과해도 `--require-integration`은 전체 연결이 검증되지 않았으면 종료 코드 2를 반환합니다. 파일이 채워진 것만으로 통합 PASS가 되지 않습니다. `scripts/benchmark.py`도 실측하지 않은 성능을 출력하지 않고 종료 코드 2로 이유를 안내합니다.

## 담당 경계

| 담당 | 경로 | 상태 |
|---|---|---|
| 1 에이전트·공통 모델 | `agent/`, `models.py` | 병합됨. 모델 구문·의존성·그래프 입력/승인 재개 수정 필요 |
| 2 의료 API | `medical_api/` | 병합됨. 단위 테스트 32개 통과, 중증 XML·시각·검색 계약 수정 필요 |
| 3 위치·검색 | `search/` | 병합됨. import·지역 정보·도구/provider 계약 수정 필요 |
| 4 메모리 | `memory/` | 구현 및 기존 단위 테스트 49개 |
| 5 가드레일 | `guardrails/` | 병합됨. 실제 그래프에 연결한 동작 검증 필요 |
| 6 화면·검증 | `web/`, `cli/`, `scripts/verify.py`, `tests/integration/` | 화면·API 직접 조회·runner 어댑터·자동 검증 구현. 기본 factory와 renderer 연결 필요 |

## 문서

- [6번 담당 가이드](docs/6번_Verification_담당가이드.md): 현재 상황, 코드 읽는 순서, 시연, 팀 협업 요청.
- [검증 기록](docs/verification.md): 실제 실행 결과와 미검증 범위.
- [2026-09-11 통합 검토](docs/review-2026-09-11.md): 최신 병합 코드의 오류, 재현 근거, 수정 순서.
- [UI 연결 계약](docs/ui-integration.md): 향후 에이전트 어댑터 연결에 필요한 규약.
- [기존 공통 인터페이스](docs/interfaces.md): 팀 설계 기준. 실제 구현 및 UI 계약과 조율 필요.
- [기존 검증 계획](docs/verification-plan.md): 구현 전 목표와 시나리오 원본.

메모리는 현재 브라우저 연결과 서버 프로세스 범위입니다. 로그인·영구 DB·공개 배포·실제 LangGraph HITL 검증은 포함하지 않습니다.
