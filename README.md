# er-agent

응급 상황에서 증상·위치를 듣고 가까운 응급실 후보를 안내하는 대화형 에이전트.

## 요구 사항

- Python 3.11+
- OpenAI API 키
- 공공데이터포털 E-Gen 응급의료정보 서비스 키
- 카카오 REST API 키

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 환경 설정

```bash
cp .env.example .env
# .env 파일에 발급받은 키를 입력
```

## 실행

```bash
python -m er_finder          # 실제 API 모드
ER_DEMO_MODE=true python -m er_finder   # fixtures 기반 데모 모드
```

## 테스트

```bash
pytest                       # 전체
pytest tests/unit            # 단위 테스트
pytest -m integration        # 시나리오 통합 테스트
pytest --cov                 # 커버리지
```

## 코드 검사

```bash
ruff check . && ruff format --check .
mypy
```

## 구조

| 경로 | 역할 | 담당 |
|---|---|---|
| `src/er_finder/agent/` | 에이전트 조립·프롬프트·도구·실행 | 조원 1 |
| `src/er_finder/medical_api/` | E-Gen API 호출·파싱·캐시 | 조원 2 |
| `src/er_finder/search/` | 지오코딩·거리·후보 선정·반경 정책 | 조원 3 |
| `src/er_finder/memory/` | 컨텍스트·상태·저장소·세션 | 조원 4 |
| `src/er_finder/guardrails/` | 분류·입력 검사·마스킹·근거 검증 | 조원 5 |
| `src/er_finder/cli/` | 대화 루프·명령·출력 | 조원 6 |

## 문서

- [docs/interfaces.md](docs/interfaces.md) — 모듈 간 공통 인터페이스
- [docs/api-contract.md](docs/api-contract.md) — 외부 API 필드·매핑
- [docs/verification.md](docs/verification.md) — 검증 결과

## 주의

의료 진단을 제공하지 않습니다. 생명이 위급한 상황에서는 즉시 119에 연락하세요.
