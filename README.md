# ER Finder · skala-er-agent

카카오·E-Gen·OpenAI API를 연결하는 응급의료기관 조회와 에이전트 상담 화면입니다. 의료기관 직접 조회와 에이전트 상담은 별도 경로로 실행됩니다. 화면에 표시할 기관 정보는 실제 API 응답을 사용합니다.

`main`의 `33e9f22`까지 반영했습니다. 공통 재시도 코드는 `http_retry.py`로 통합되었습니다. 공통 모델 구문과 메모리 import 계약 오류는 upstream에 남아 있어 전체 상담 연결을 막을 수 있습니다. 현재 실행 결과와 남은 오류는 [검증 기록](docs/verification.md)을 확인하세요.

## 실행

Python 3.11 이상이 필요합니다. 프로젝트 루트에서 실행합니다.

```bash
uv sync --frozen --extra dev
uv run --frozen streamlit run streamlit_app.py
```

설치 후 `er-finder` 또는 `python -m er_finder`도 같은 웹 화면을 실행합니다. 기본 주소는 localhost입니다.

기존 `.env` 또는 실행 환경에 다음 키를 설정합니다. 필요한 항목은 [.env.example](.env.example)을 참고하세요. 화면은 키의 설정 여부만 표시하며 키 값을 출력하지 않습니다.

```dotenv
OPENAI_API_KEY=...
KAKAO_REST_API_KEY=...
EGEN_SERVICE_KEY=...
```

## 사용 흐름

| 탭 | 동작 |
|---|---|
| 의료기관 조회 | 좌표와 반경을 입력하고 조회하면 주변 기관 정보를 요청합니다. 기관명·거리·대표전화 등을 확인하고 기관을 선택해 상세 정보를 조회합니다. |
| 에이전트 상담 | 연결 확인 후 위치와 증상을 입력합니다. runner가 반환한 후보 선택과 방문 계획 승인·거절을 전달합니다. 연결 오류는 해당 상태로 표시합니다. |
| 연결 상태 | OpenAI·카카오·E-Gen 키 설정 여부와 에이전트 연결 결과를 확인합니다. 설정됨은 API 인증 성공을 의미하지 않습니다. |

기관 목록은 병상이나 진료 수용 가능 여부의 확정 결과가 아닙니다. 누락된 정보는 확인 불가로 표시하며 방문 전에 병원 대표전화로 확인해야 합니다. 위급한 상황에서는 즉시 119에 연락하세요.

화면 재실행만으로 API를 다시 호출하지 않습니다. 새 대화는 대화와 승인 대기를 초기화하고, 기록 전체 삭제는 해당 브라우저의 저장 정보와 조회 기록도 제거합니다. 주소는 동의 후 저장하며, 방문 계획 저장은 병원 예약이나 접수가 아닙니다. 저장소는 서버 메모리이므로 영구 보관을 제공하지 않습니다.

## 검증

```bash
uv run --frozen python scripts/verify.py
uv run --frozen python scripts/verify.py --require-integration
```

검증 도구는 live 테스트를 제외하고 Python 소켓의 외부 통신을 차단합니다. 로컬 fixture와 주입한 runner를 사용한 화면 계약 검증은 실제 LLM·LangGraph 승인 재개·API 호출 검증과 구분합니다. 수집 오류가 남으면 실행 가능한 테스트를 계속 기록하되 전체 결과는 FAIL입니다.

`verification-results/report.json`, `junit.xml`, `pytest.log`에 실행 근거를 저장합니다. 전체 연결을 검증하지 못하면 `integration.status`는 BLOCKED 또는 NOT_VERIFIED이며, 파일이 존재하거나 단위 테스트가 통과한 것만으로 통합 PASS를 표시하지 않습니다. 추천 정확도와 지연 시간은 별도 실측 전까지 미측정입니다.

## 담당과 문서

| 담당 | 경로 |
|---|---|
| 1 에이전트·공통 모델 | `agent/`, `models.py` |
| 2 의료 API | `medical_api/` |
| 3 위치·검색 | `search/` |
| 4 메모리 | `memory/` |
| 5 가드레일 | `guardrails/` |
| 6 화면·검증 | `web/`, `cli/`, `scripts/verify.py`, 화면 테스트 |

- [6번 담당 가이드](docs/6번_Verification_담당가이드.md)
- [UI 연결 계약](docs/ui-integration.md)
- [검증 기록](docs/verification.md)
- [공통 인터페이스](docs/interfaces.md)
- [e97341a 시점 통합 검토](docs/review-2026-09-11.md): 이전 커밋의 검토 기록이며 현재 오류 목록과 구분합니다.

CI는 `Web and verification tooling`(6번)과 `All modules integration`(전체)을 각각 실행합니다. 6번 통과를 전체 서비스 통과로 해석하지 않습니다. 로컬에서 담당 범위만 실행하려면 `python scripts/verify.py --scope web`을 사용합니다. 기본 실행은 전체 범위입니다.
