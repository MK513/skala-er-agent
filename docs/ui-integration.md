# Streamlit ↔ 에이전트 연결 계약 제안

이 문서는 **조원 6이 준비한 화면 포트**다. 팀 공통 `models.py` 또는 1번 runner 구현을 이미 확정했다고 뜻하지 않는다. 현재 `PreviewBackend`와 `RunnerBackend`가 있으며, 기본 runner factory는 기존 모듈·provider 계약 오류를 명시하고 연결을 차단한다. 주입한 runner로 화면 어댑터를 검증했으며 실제 그래프 연결 완료는 아니다.

2026-09-11 업데이트: `e97341a`에 실제 runner와 2·3·5번 구현이 병합되었다. 현재는 runner의 import, 검색/provider 계약, 메시지 전달과 승인 재개에 오류가 있어 바로 연결할 수 없다. 아래 포트는 여전히 연결 제안이며, [최신 통합 검토](review-2026-09-11.md)의 선행 오류를 수정한 뒤 어댑터를 구현한다.

## 구조

```text
streamlit_app.py → web/app.py → WebSession → Backend Protocol
                                           └ PreviewBackend
                                              └ ERFinderStore + VisitPlanService

향후 Backend 구현체 추가 → 1번 runner → 2·3·5번 모듈과 실제 HITL 그래프
```

`web/contracts.py`의 `UIReply`, `UIHospital`은 표시용 모델이다. 이는 실제 도구 근거가 검증되었다는 보증이 아니다. 현재 데이터 출처는 `web/preview.py`에 선언된 고정 합성 값이다. 실제 연결 시 runner의 검증된 최종 결과를 이 모델로 변환한다.

## 필요한 호출

| 포트 | 화면이 기대하는 동작 |
|---|---|
| `chat(text, *, transport, force_refresh=False) -> WebResult` | 새 입력 이벤트에서만 조회. force_refresh는 마지막 검색을 다시 조회하며 선택/승인을 재실행하지 않음 |
| `select_hospital(hpid) -> WebResult` | 현재 후보 안에서만 선택. 저장하지 않고 승인 대기 생성 |
| `approve(approved: bool) -> WebResult` | 현재 승인 대기 1건을 한 번만 처리. 실제 연결에서는 runner의 interrupt/resume 사용 |
| `reset()` | 대화·현재 위치·후보·승인 대기를 제거하고 동의 프로필 유지 |
| `forget()` | 해당 사용자 대화와 프로필 전체 삭제 |
| `user_id`, `profile` | 브라우저별 ID와 현재 ERFinderStore 프로필 API |

`WebResult`의 필드는 `reply`, `pending_approval`, `note`다. 현재 pending은 4번의 `PendingVisitPlan` 타입을 사용한다. 실제 runner가 dict/다른 객체를 반환하면 어댑터에서 변환한다.

`WebSession`을 기본 생성하면 미리보기가 만들어진다. 향후 실제 어댑터를 주입할 때에는 `WebSession(backend=adapter)` 형태를 사용한다. **현재 UI에는 연결 상태에 따른 활성화 분기가 있다. 기본 factory의 provider·모델 조립은 아직 연결되지 않았다.** 포트만 구현한 것으로 실제 서비스가 자동 활성화되지는 않는다.

## 팀원에게 먼저 확인할 사항

1. **1번:** 실제 runner 생성 방식, 동기/비동기 실행, `chat`/승인 재개 응답 타입, 예외 규약, 검색 취소, 세션 종료. 위급 안내를 조회 완료 전에 표시할 콜백 또는 스트림 이벤트가 필요하다.
2. **2번:** 병원 고유 ID, 전화번호 없는 경우, 정상 캐시/실패 대체 캐시, 원본 갱신 시각과 `is_cached`·`is_stale` 의미. 녹화 fixture의 출처·시각·비식별화.
3. **3번:** 도보 반경 정책. 기존 `interfaces.md`는 5/10/20/30, `memory/context.py`는 도보 3/6/9/12, 메모리 테스트는 3/10/20/30으로 서로 다르다. UI는 반환된 반경만 표시하고 확대 규칙을 정하지 않는다.
4. **4번:** 실제 저장소의 전체 삭제 API, 체크포인트 정리, 저장 실패 시 재승인 정책. 현재 PreviewBackend는 자신만 소유한 InMemoryStore를 폐기해 전체 삭제한다. 공유/영구 저장소로 바꾸면 이 방법을 쓰면 안 된다.
5. **5번:** 입력 마스킹 완료 시점, critical 즉시 안내 이벤트, 도구 근거 검증 완료 결과. 현재 표시용 정규식은 일부 전화·주민번호만 가리며 실제 가드레일을 대체하지 않는다.

## 실제 연결 이후의 인수 검증

- 키 누락/잘못된 인증, 타임아웃, 부분 데이터, 위치 재질문에서 예외가 화면에 유출되지 않는지.
- critical 입력의 119 안내가 외부 조회 완료보다 먼저 도착하는지.
- 도구 원본과 카드의 병상·전화·ID가 일치하는지.
- 승인 전 도구 쓰기 0회, 거절 후 0회, 승인 후 1회, Streamlit rerun 후 추가 0회.
- 시나리오 데모가 아닌 실제 그래프의 상태 유지·세션 격리·삭제.
- 명시적으로 허용된 실제 API 테스트와 별도 성능 계측.

UI 시연 테스트의 통과를 위 항목의 통과로 옮겨 적지 않는다.
