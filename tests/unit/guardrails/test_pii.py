"""Synthetic personal identifiers must not reach downstream messages unmasked."""

import re

import pytest

from er_finder.guardrails.pii import PII_PATTERN, mask_pii


@pytest.mark.parametrize(
    "identifier",
    [
        "010-1234-5678",
        "01012345678",
        "011 123 4567",
        "+82 10 1234 5678",
        "02-1234-5678",
        "031 123 4567",
        "900101-1234567",
        "9001011234567",
    ],
)
def test_masks_full_phone_and_registration_number_spans(identifier):
    assert mask_pii(f"연락 정보: {identifier}. 증상은 발열입니다.") == (
        "연락 정보: [개인정보 삭제]. 증상은 발열입니다."
    )
    # The same exported pattern is also consumed directly by PIIMiddleware.
    assert re.fullmatch(PII_PATTERN, identifier) is not None


def test_normalizes_disguised_phone_numbers_before_masking():
    assert mask_pii("연락처 ０１０-１２３４-５６７８, 주민번호 900101-1\u200b234567") == (
        "연락처 [개인정보 삭제], 주민번호 [개인정보 삭제]"
    )


@pytest.mark.parametrize(
    "text",
    [
        "서울 강남구 테헤란로 123, 38.5도 발열이 있어요.",
        "진료 문의는 119, 반경은 5 km입니다.",
        "주문번호 990101234567899",
        "접수번호 99001011234567123",
    ],
)
def test_preserves_non_identifiers_and_longer_digit_sequences(text):
    assert mask_pii(text) == text
