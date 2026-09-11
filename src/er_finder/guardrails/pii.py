import re
import unicodedata

# 정규 표현식 패턴 (전화번호, 주민등록번호 등)
PII_PATTERN = (
    r"(?<!\d)(?:\d{6}[-\s]?[1-4]\d{6}|"
    r"(?:\+82[-\s]?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}|"
    r"0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})(?!\d)"
)


def normalize(text: str) -> str:
    """
    입력 텍스트를 정규화
    """
    return unicodedata.normalize("NFKC", text).replace("\u200b", "").replace("\ufeff", "")


def mask_pii(text: str) -> str:
    """
    입력 텍스트에서 PII를 마스킹
    """
    normalized_text = normalize(text)
    masked_text = re.sub(PII_PATTERN, "[개인정보 삭제]", normalized_text)
    return masked_text
