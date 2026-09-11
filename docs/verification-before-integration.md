# 검증 기록 · 조원 6

> 과거 기록: `8e996da`에서 실행한 결과다. 이후 1·2·3·5번 모듈 병합으로 전체 검증 결과가 달라졌다. 현재 상태는 [verification.md](verification.md)를 따른다.

기준 저장소: `skala-er-agent`, 브랜치 `feature/verification`.

- 실행 시작: 2026-09-11T12:02:04.758445+09:00
- 기준 커밋: `8e996da33c537b2162b9650531c302c38c158dc5` + 이번 미커밋 변경분
- 환경: macOS, Python 3.14.6, Streamlit 1.63.0, 프로젝트 전용 `.venv`
- 데이터 출처: `web/preview.py`의 고정 합성 시나리오. 녹화 API 데이터 아님.
- 실제 API·LLM·임상 평가·추천 성능 측정: 수행하지 않음.

## 실제 실행 결과

```bash
.venv/bin/python scripts/verify.py --output verification-results
```

| 범위 | 결과 | 근거 |
|---|---|---|
| 전체 오프라인 테스트 | 104 PASS, 실패 0, 오류 0, skip 0 | `verification-results/junit.xml` |
| 기존 4번 메모리 단위 테스트 | 49 PASS | `tests/unit/memory/` |
| 화면 상태·메모리 연결 | 15 PASS | `tests/unit/web/test_state.py` |
| Streamlit 사용자 흐름 | 20 PASS | `tests/integration/test_streamlit.py` |
| 검증 도구 자체 회귀 테스트 | 20 PASS | `tests/unit/verification/test_verify.py` |
| 전체 서비스 연결 | BLOCKED | 빈 백엔드 파일 19개 + fixture 3개 |
| 실제 API 성능/정확도 | NOT_RUN | 미구현 runner, 실측 없음 |
| GitHub Actions 원격 실행 | NOT_RUN | 워크플로 작성, push/PR 실행 안 함 |

JSON/JUnit/log는 `verification-results/`에 생성했고 git 추적에서 제외했다. 위 pytest 실행에 걸린 시간은 **테스트 실행 시간**으로, 응급실 추천 P90에 사용할 수 없다.

## 이번에 재현하고 검사한 사용자 흐름

- 가상 후보 3곳과 거리·병상·전화 확인 불가·갱신 시각 표시.
- 화면 rerun만으로 대화가 늘거나 방문 계획이 저장되지 않음.
- 후보 선택 후 승인 전 Store 0건, 승인 후 1건, 거절 후 0건.
- 결정 후 rerun/중복 승인 시 추가 저장 없음.
- 브라우저별 ID·대화·주소·방문 계획 격리.
- 새 대화에서 프로필 유지, 전체 삭제에서 프로필 제거.
- 기본 주소 동의 없으면 저장 금지, 동의 철회 시 삭제.
- 시나리오·이동수단·실제 모드 변경 시 기존 후보/승인 취소.
- **설정 변경과 승인 클릭을 같은 이벤트에 넣어도 이전 계획 저장 금지.** 리뷰 중 발견하여 실패 재현 후 수정했다.
- 위치 없는 고정 예시의 두 번째 입력에서 후보 표시.
- 오류·119·갱신 지연 화면과 실제 모드 차단.
- 일반적인 전화번호/주민번호 표시 가림. 전체 개인정보 보호/실제 가드레일 검증은 아님.
- JUnit 오류·실패·timeout·test 없음·전체 skip을 통과로 기록하지 않음.
- **모든 테스트가 skip이면 `NO_TESTS`와 비정상 종료.** 실제 자식 pytest 프로세스로 실패 재현 후 수정했다.
- `--require-integration` 실제 실행: 로컬 PASS여도 종료 코드 2, 전체 연결 BLOCKED.
- 벤치마크 실제 실행: 종료 코드 2, 성능 미측정 사유 출력.

## 브라우저 점검

2026-09-11 localhost:8502의 Chrome에서 초기 화면, 후보 카드, 두 번째 가상 병원 선택,
승인 후 가상 응급센터 B 저장 기록, 실제 모드 입력 비활성화를 직접 확인했다.
상단 제목 영역이 가려지는 부분은 여백을 조정했다. AppTest와 별도로 수행한 수동 확인이다.

## 코드 품질 검사

- `ruff check .`: PASS.
- 이번 변경 Python 파일의 `ruff format --check`: PASS.
- `mypy --python-version 3.14 --follow-imports=silent src/er_finder/web src/er_finder/cli/app.py`: PASS (7개 파일).
- 저장소 전체 타입 검사는 완료 조건을 충족하지 않는다. 같은 Python 3.14 대상으로 실행하면 기존 `memory/state.py:65`, `memory/store.py:107`, `memory/visit_plan.py:51`에 타입 오류 3건이 남는다. 다른 조원 코드는 수정하지 않았다.
- 기본 `mypy` 설정은 Python 3.11인데 현재 3.14 환경의 NumPy 타입 스텁이 3.12+ 구문을 사용해 우선 구문 오류가 발생한다. 최소 지원 버전 검증은 해당 Python 가상환경에서 추가로 해야 한다.
- 전체 `ruff format --check .`에는 기존 `memory/context.py` 1개 파일의 포맷 차이가 남는다. 변경 범위는 모두 통과했다.
- `uv sync --frozen --extra dev --offline`: 이 환경의 다운로드된 캐시에서 성공. 실제 import 경로가 `skala-er-agent/src/er_finder`임을 확인했다.

## 지금 검증하지 못한 것

실제 에이전트 그래프, LangGraph HITL interrupt/resume, 모델 분류, 입력 공격 차단,
도구 원본 근거 검증, 실제 위치·거리·반경 확대, API 재시도·캐시, 실제 API 키 설정,
후보 정확도 90%, 첫 추천 P90 15초, 재질의 8초, 모델/API 호출량, 인증·영구 저장·배포.

이 항목은 화면 데모 PASS로 대체할 수 없다. 기존 검증 목표표는
[verification-plan.md](verification-plan.md)에 계획으로 보존했다. 기존 API 계약의 녹화일
표기도 실제 파일 증거가 아니며 sample fixture 3개는 여전히 빈 파일이다.

다음 단계는 [UI 연결 계약](ui-integration.md)에 따라 1번 runner와 2·3·5번 모듈을
연결하고, 출처가 확인되는 시나리오를 추가하는 것이다.
