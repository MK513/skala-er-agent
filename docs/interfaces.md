# 공통 인터페이스 (조원 1)

설계서 `2.4 Structured Output`, `2.5 Tool`, `3.1 Context`, `3.2 Middleware`에 대응하는 모듈 간 계약이다.
여기 적힌 타입·시그니처는 모든 조원이 공유하는 경계이므로, 변경 시 이 문서를 먼저 고치고 공유한다.

## 1. 공통 데이터 모델 (`er_finder/models.py`)

모두 Pydantic 모델. 모델의 Structured Output 스키마이자 모듈 간 전달 타입으로 함께 쓴다.

### `TriageAssessment` — 분류 모델(gpt-4o-mini) 출력

| 필드 | 타입 | 필수 | 제약 |
|---|---|---|---|
| `severity` | `Literal["critical","urgent","standard"]` | O | 3단계 고정 |
| `condition` | `Literal["심근경색","뇌출혈","뇌졸중","중증외상","화상","분만"] \| None` | X | `critical`/`urgent`일 때만 값 허용 |
| `injection` | `bool` | O | `True`면 가드레일 차단 |
| `confidence` | `float` | O | 0.0~1.0, 0.6 미만이면 `severity` 한 단계 상향 |

### `HospitalCandidate` — 후보 병원

| 필드 | 타입 | 필수 | 제약 |
|---|---|---|---|
| `hpid` | `str` | O | 도구 결과에 존재하는 값만 |
| `name` | `str` | O | 도구 결과와 동일 |
| `distance_km` | `float` | O | 0.0 이상, 소수 첫째 자리 |
| `er_beds_available` | `int \| None` | O | `None`이면 '확인 불가'로 표기 |
| `beds_updated_at` | `str \| None` | O | `hvidate` 값, 15분 초과 시 `stale=True` |
| `accepts_condition` | `Literal["yes","no","unknown"]` | O | `standard`이면 항상 `unknown` |
| `er_tel` | `str \| None` | O | 도구 결과와 동일 |
| `address` | `str` | O | 도구 결과와 동일 |

### `ERSearchReply` — 최종 응답

| 필드 | 타입 | 필수 | 제약 |
|---|---|---|---|
| `severity` | `Literal["critical","urgent","standard"]` | O | |
| `call_119_first` | `bool` | O | `severity=critical`이면 항상 `True` |
| `search_radius_km` | `int` | O | 5, 10, 20, 30 중 하나 |
| `hospitals` | `list[HospitalCandidate]` | O | 0~3개, `distance_km` 오름차순 |
| `no_candidate_reason` | `str \| None` | X | `hospitals`가 비면 필수 |
| `data_timestamp` | `str` | O | ISO 8601 |
| `next_action` | `str` | O | 80자 이내, 진단·처방 표현 금지 |
| `disclaimer` | `str` | O | 고정 문장과 완전 일치 |

고정 고지 문구: `"응급실 상황은 수시로 변하므로 방문 전 전화 확인을 권장합니다"`

## 2. 도구 인터페이스 (`er_finder/agent/tools.py`)

`tools.py`는 각 조원이 구현한 함수를 `@tool`로 감싸 등록만 한다. 실제 로직은 구현 모듈에 둔다.

| 도구 | 입력 | 출력 | 구현 모듈 | 담당 |
|---|---|---|---|---|
| `geocode` | `query: str` | `dict(lat, lon, address, sido, sigungu, found)` | `search/geocoder.py` | 조원 3 |
| `list_nearby_ers` | `lat: float, lon: float, radius_km: int = 5` | `list[dict(hpid, name, distance_km, er_tel, lat, lon)]` | `medical_api/client.py` + `search/distance.py` | 조원 2·3 |
| `get_er_bed_status` | `sido: str, sigungu: str, hpids: list[str]` | `list[dict(hpid, name, er_beds_available, beds_updated_at, stale)]` | `medical_api/client.py` + `cache.py` | 조원 2 |
| `get_severe_acceptance` | `sido: str, sigungu: str, condition: str` | `list[dict(hpid, name, acceptable)]` | `medical_api/client.py` | 조원 2 |
| `get_er_detail` | `hpid: str` | `dict(name, address, er_tel, main_tel, hours)` | `medical_api/client.py` | 조원 2 |
| `save_visit_plan` | `hpid: str, name: str, symptom_summary: str` | `dict(saved, visit_id)` | `memory/visit_plan.py` + `store.py` | 조원 4 |

호출 순서 의존성:

```
geocode → list_nearby_ers → get_er_bed_status
        → (critical/urgent 且 condition 존재) get_severe_acceptance
        → get_er_detail × 3 → (HITL 승인 후) save_visit_plan
```

반경 확대는 `list_nearby_ers`부터 다시 시작한다. 확대 최대 3회(5 → 10 → 20 → 30km).

도구 규약:
- 모든 도구는 예외를 밖으로 던지지 않는다. 실패는 결과 dict의 플래그(`found=False`, 빈 목록, `acceptable=None`, `stale=True`)로 표현한다.
- 도구는 읽기 전용이다. 유일한 쓰기 도구 `save_visit_plan`은 HITL 승인 이후에만 실행된다.
- E-Gen은 XML을 돌려주므로 도구 경계를 넘기 전에 dict로 변환한다(조원 2).
- `get_er_bed_status`는 시도·시군구 단위 응답을 `hpids`로 필터링해 모델이 긴 목록을 읽지 않게 한다.

## 3. Context 경계 (`er_finder/memory/`)

| 항목 | 유형 | 타입 | 모듈 | 접근 주체 |
|---|---|---|---|---|
| `user_id` | Runtime Context | `str` | `context.py` | 전체 미들웨어, `save_visit_plan` |
| `transport` | Runtime Context | `Literal["walk","car","transit"]` | `context.py` | `ProfileDynamicPrompt`, `list_nearby_ers` |
| `messages` | State | `list[Message]` | `state.py` | `before_model` |
| `current_location` | State | `dict(lat, lon, sido, sigungu)` | `state.py` | `list_nearby_ers`, `get_er_bed_status` |
| `triage` | State | `TriageAssessment` | `state.py` | 도구 선택, `get_severe_acceptance` |
| `search_radius_km` | State | `int` | `state.py` | `list_nearby_ers`, 반경 확대 판단 |
| `candidates` | State | `list[HospitalCandidate]` | `state.py` | `EvidenceCheck`, 최종 응답 |
| `bed_cache` | State (임시) | `dict[str, tuple[list, float]]` | `medical_api/cache.py` | `get_er_bed_status` (60초) |
| `home_address` | Store | `str` | `store.py` | `ProfileDynamicPrompt` |
| `recent_visits` | Store | `list[dict]` | `store.py` | `ProfileDynamicPrompt` |

- 체크포인터: `InMemorySaver`, `thread_id = user_id` (`memory/session.py`)
- 세션 간 프로필: `InMemoryStore` (`memory/store.py`)
- 사용자 위치(`current_location`)는 세션 종료 시 폐기한다. Store에는 동의한 `home_address`와 `recent_visits`만 남는다.

## 4. 모듈 경계 요약

- `search` ← `medical_api`: `search`는 좌표·거리·정렬만 담당하고, 병상/중증 데이터는 `medical_api`가 정규화한 dict만 받는다.
- `agent` ← `guardrails`: `guardrails/middleware.py`가 미들웨어 객체를 노출하고, `agent/factory.py`가 조립 순서대로 배치한다.
- `agent` ← `memory`: `factory.py`는 `session.py`의 체크포인터와 `store.py`의 Store를 주입만 받는다.
- `cli` ← `agent`: `cli/app.py`는 `agent/runner.py`의 실행·승인 재개 인터페이스만 호출하고 내부 상태를 직접 만지지 않는다.
- `cli` ← `models`: 렌더링은 `ERSearchReply`만 입력으로 받는다.

## 5. 미들웨어 조립 순서 (`agent/factory.py`)

```
before_agent   : EmergencyInputGuard (Custom)
before_model   : ProfileDynamicPrompt (Custom) → PIIMiddleware (Built-in)
wrap_model_call: ModelCallLimitMiddleware (run_limit=10)
wrap_tool_call : ToolRetryMiddleware (max_retries=2, backoff 1s)
after_model    : HumanInTheLoopMiddleware (save_visit_plan)
after_agent    : EvidenceCheckMiddleware (Custom)
```

## 6. 오류 처리 규약

| 상황 | 처리 | 사용자에게 보이는 형태 |
|---|---|---|
| 외부 API 타임아웃·5xx·429 | 2회 재시도(백오프 1초) | 재시도 후에도 실패하면 아래로 |
| 재시도 후 실패 + 캐시 있음 | 60초 캐시 반환, `stale=True` | '갱신 지연' 표시 + 전화 확인 권고 |
| 재시도 후 실패 + 캐시 없음 | 빈 목록 반환 | 모델이 상황을 설명 |
| `geocode` 0건 | `found=False` | 위치를 다시 묻는 재질문 |
| 중증 수용 조회 실패 | `acceptable=None` | `accepts_condition="unknown"` → '확인 불가' |
| `get_er_detail` 실패 | 목록 조회 값으로 대체 | 누락 필드는 '확인 불가' |
| 모델 호출 10회 도달 | 현재 후보로 종료 응답 생성 | 정상 종료 |
| 반경 3회 확대 후 후보 0 | `no_candidate_reason` 기재 | 후보 없음 + 119 안내 |
| `save_visit_plan` 승인 거절 | 실행하지 않음 | 저장 없이 대화 계속 |
| `save_visit_plan` 저장 실패 | `saved=False`, 재시도 없음 | 저장 실패 안내 |

로깅 규약: API 키, 마스킹 전 전화번호·주민번호는 로그에 남기지 않는다.
