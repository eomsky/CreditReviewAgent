"""Input guardrails for abusive, unsafe, and clearly out-of-scope requests."""

from __future__ import annotations

import re
from dataclasses import dataclass


ABUSIVE_PATTERNS = (
    r"\b(?:fuck|shit|bitch)\b",
    r"(?:씨발|시발|병신|개새끼|좆같|미친놈|꺼져)",
)
HARMFUL_PATTERNS = (
    r"(?:해킹|악성코드|피싱메일).*(?:만들|작성|침투)",
    r"(?:개인정보|주민번호|비밀번호).*(?:훔치|탈취|수집)",
)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    allowed: bool
    response: str | None = None
    category: str | None = None


def check_input(text: str) -> GuardrailResult:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in ABUSIVE_PATTERNS):
        return GuardrailResult(
            False,
            "모욕적이거나 공격적인 표현에는 답변하지 않습니다. 여신심사와 관련된 질문을 정중하게 입력해 주세요.",
            "abusive_language",
        )
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in HARMFUL_PATTERNS):
        return GuardrailResult(
            False,
            "개인정보 침해나 불법 행위를 지원하는 요청에는 답변할 수 없습니다.",
            "harmful_request",
        )
    return GuardrailResult(True)
