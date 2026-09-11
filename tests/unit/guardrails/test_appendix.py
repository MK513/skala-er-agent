import pytest

from er_finder.safety import assess_input

APPENDIX = [
    "의식 없",
    "의식이 없",
    "쓰러졌",
    "깨어나지 않",
    "반응이 없",
    "실신",
    "기절",
    "숨을 못",
    "숨쉬기 힘들",
    "숨이 안",
    "호흡 곤란",
    "호흡이 멈",
    "숨을 안 쉬",
    "입술이 파랗",
    "질식",
    "심한 흉통",
    "가슴을 쥐어짜",
    "가슴 통증이 심",
    "심정지",
    "맥박이 없",
    "피가 멈추지 않",
    "대량 출혈",
    "피를 많이",
    "피가 계속",
    "토혈",
    "피를 토",
    "경련",
    "발작",
    "마비",
    "한쪽 팔에 힘",
    "말이 어눌",
    "얼굴이 한쪽으로",
    "극심한 두통",
    "추락",
    "교통사고",
    "심한 화상",
    "감전",
    "물에 빠",
    "음독",
    "약을 많이 먹",
]


@pytest.mark.parametrize("phrase", APPENDIX)
def test_every_appendix_phrase_forces_critical(phrase: str):
    assert assess_input(f"환자가 {phrase} 증상이 있어요").triage.severity == "critical"