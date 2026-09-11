# 검증 기록 · 조원 6

기준: `main`의 `e97341a`와 `feature/verification`의 로컬 Streamlit·검증 변경분. 백엔드 오류 수정은 보류하고 화면 실행과 연결 경계를 검증했다.

## 현재 실행 결과

2026-09-11T05:06:10.524000+00:00 (UTC), macOS / Python 3.14.6 / Streamlit 1.63.0에서 실행했다.

```bash
.venv/bin/python scripts/verify.py --output verification-results
```

- 전체 오프라인 검증: **174 PASS, 수집 오류 6건, 전체 FAIL**.
- 메모리 49개, 의료 API 32개, 화면 상태 15개, Streamlit 사용자 흐름 26개, runner 어댑터 18개, API 조회 화면 6개, 검증 도구 24개, 주입한 runner를 사용하는 실제 모드 화면 흐름 4개가 통과했다.
- 기존 agent의 모델 구문 오류 1건, search의 retry import 오류 4건과 없는 demo_provider import 1건은 그대로 남는다.
- 통합 상태: **BLOCKED**. 상세 원인은 [백엔드 통합 검토](review-2026-09-11.md)를 따른다.
- 이번 화면·검증 코드 Ruff와 화면 파일 format 검사: PASS. 전체 저장소 Ruff에는 기존 백엔드 오류가 남는다.
- 실제 API·실제 LLM 호출, 임상 정확도, 추천 지연 시간 측정: 수행하지 않음.

자동 보고서는 `verification-results/report.json`, `junit.xml`, `pytest.log`다. 로컬 실행 생성물로 Git에서 제외한다. pytest 실행 시간은 추천 P90이 아니다.

## 화면 실행과 검토

```bash
uv sync --frozen --extra dev
uv run --frozen streamlit run streamlit_app.py
```

로컬 `http://localhost:8503`에서 Streamlit 서버 실행 및 Chrome의 초기 실제 모드, 연결 상태와 키 누락 안내를 확인했다.

- **응급실 찾기:** 대화·후보 카드·선택·저장 승인·새 대화·삭제 UI. 실제 runner 어댑터의 성공 흐름은 주입한 로컬 테스트 runner로 검증한다. 실제 프로젝트 그래프의 통과를 뜻하지 않는다.
- **의료 API 조회:** 조회 버튼에서만 기존 `medical_api.client.list_nearby_ers()`를 호출한다. 기존 parser와 MockTransport의 녹화 XML로 표 표시, 빈 응답·오류, 세션 격리와 rerun 시 추가 호출 0회를 확인했다. 병상·중증 추천을 수행하지 않는다.
- **연결 상태:** API 키의 설정 여부만 보여준다. 설정됨은 인증 성공을 의미하지 않는다.
- **화면 검토용 예시:** 고정 합성 카드와 승인 흐름을 별도 모드에서 확인한다. 실제 모드와 기록이 섞이지 않는다.
- 모드 변경과 승인·주소 저장/삭제를 같은 이벤트로 넣어도 이전 모드의 작업을 실행하지 않는다.
- 전체 삭제는 양쪽 모드의 저장 정보와 API 조회 기록을 제거한다.

현재 기본 runner factory는 모듈 import와 provider 계약 준비 여부를 확인하고 연결을 차단한다. 백엔드 import 오류를 고친 뒤에도 실제 provider 및 모델을 생성하는 factory 연결 작업이 필요하다. API 키만 채운 것으로 전체 에이전트가 완성되지 않는다.

기존 메모리만 병합되어 있던 시점의 104 PASS 기록은 [이전 검증 기록](verification-before-integration.md)에 보존했다. 현재 수치로 사용하지 않는다.
