"""medical_api 테스트에서만 쓰는 pytest fixture."""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "egen"


@pytest.fixture
def egen_fixture():
    """이름으로 tests/fixtures/egen/ 안의 XML 파일을 읽어주는 함수를 돌려준다.

    사용 예: egen_fixture("nearby_gangnam.xml")
    """

    def _load(name: str) -> str:
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")

    return _load
