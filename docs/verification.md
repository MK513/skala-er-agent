# 검증 기록 · 조원 6

기준: upstream `main`의 `00971aa` 이후 통합 수정. 실제 API 확인은 로컬 환경에서 수행했다.

## 수정 범위

- 실제 `ERFinderContext`·`ERFinderStore`·`SessionManager`·`VisitPlanService` 연결.
- LangGraph 메시지 입력, 실제 interrupt/resume, 서버의 도구 순서와 후보 근거 검증.
- 선택한 병원만 승인 후 한 번 저장. 거절·중복 승인·위치 변경·이전 후보 차단.
- 기관 주소의 시도·시군구, KST 시각, `MKioskTy` 태그와 수용값, 비정상 숫자 처리.
- API 실패와 정상 빈 응답 분리, 조회 실패 시 추가 호출 중단, 캐시·강제 갱신 표시.
- 개인정보 마스킹, 입력 범위 검사, 위급 규칙의 모델 호출 전 안내.
- 최신 방문 기록 페이지 조회와 엄격 체크포인트 역직렬화.
- 좌표 직접 입력 및 프로젝트 `.env` 우선 로컬 실행기.

## 실제 API 확인

2026-09-11 로컬 키로 실행했다. 공개 강남역 기본좌표와 저장소의 **합성 테스트 증상**을 사용했으며 사용자의 실제 위치·건강정보를 수집하지 않았다. 카카오는 호출하지 않았다.

`verification-results/live-full-flow.json`:

- 실제 OpenAI 모델과 E-Gen으로 일반 검색 성공. 반경 5km, 실제 기관 3곳의 병상·전화·주소 확인.
- 검색 완료 약 21초, 메인 모델 5회. 이 1회 실측은 일반 성능 보장이 아니다.
- 실제 선택 → 거절: 저장 0회. 다시 선택 → 승인: 저장 1회. 중복 승인: 추가 저장 0회.
- 승인·거절을 포함한 전체 확인 약 36.8초. 별도 테스트 메모리는 종료 후 제거했다.

`verification-results/live-urgent-flow.json`:

- 실제 중증 수용 조회 성공. 해당 조건의 수용값이 `yes`인 기관 2곳을 반환했다.
- 검색 처리 약 14.8초, 연결·정리를 포함한 전체 약 16.8초, 메인 모델 5회.

모델·API 요청은 실제 실행이며, 합성 입력의 응급도·추천 적절성에 대한 임상 검증을 의미하지 않는다.

## 오프라인 회귀

```bash
.venv/bin/python scripts/verify.py --scope all --output verification-results/local-integration
```

최종 실행 결과 **329개 통과, 실패·오류·건너뜀 0개**. Ruff와 `git diff --check`도 통과했다. 상세 근거는 생성된 `report.json`, `junit.xml`, `pytest.log`를 따른다. 실제 메모리·검색·LangGraph와 녹화된 API XML을 사용하는 테스트를 포함한다. 외부 소켓 통신은 차단하며 테스트용 provider를 운영 화면에 연결하지 않는다. 카카오 JSON과 시나리오 JSON의 출처·합성 여부를 자료 안에 명시했다.

`integration.status=NOT_VERIFIED`는 오프라인 명령만으로 실 API/임상 검증 PASS를 선언하지 않는다는 뜻이다. 실제 실행의 근거는 위 별도 보고서에서 확인한다. API 데이터는 수시로 바뀌므로 후보 수·병상 수는 재실행 시 달라질 수 있다.

## 로컬 검토

```bash
.venv/bin/python scripts/run_local.py
```

http://localhost:8503 에서 **주소 검색 없이 좌표로 조회** → 위치 입력 → **에이전트 연결 확인** → **에이전트 상담** 순서로 확인한다. `.env`는 Git에서 제외되며 실제 키는 화면·로그·문서에 기록하지 않는다. 서버 메모리 저장은 영구 저장이나 병원 예약이 아니다.

이전 시점의 [검토 기록](review-2026-09-11.md)과 [기존 검증 기록](verification-before-integration.md)은 이력으로 보존한다.
