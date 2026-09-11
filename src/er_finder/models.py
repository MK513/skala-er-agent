from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "urgent", "standard"]
Condition = Literal["심근경색", "뇌출혈", "뇌졸중", "중증외상", "화상", "분만"]
Radius = Literal[5, 10, 20, 30]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class TriageAssessment(StrictModel):
    severity: Severity
    condition: Condition | None = None
    injection: bool
    confidence: float = Field(ge=0, le=1)
    confidence_escalted: bool = False

class HospitalCandidate(StrictModel):
    hpid: str = Field(min_length=1)
    name: str
    distance_km: float
    er_beds_available: int | None
    beds_updated_at: str | None
    accepts_condition: Literal["yes", "no", "unknown"]
    er_tel: str | None
    address: str

class ERSearchReply(StrictModel):
    severity: Severity
    call_119_first: bool
    search_radius_km: Radius
    hospitals: list[HospitalCandidate] = Field(max_length=3)
    no_candidate_reason: str | None = None
    data_timestamp: str
    next_action: str = Field(min_length=1, max_length=80)
    disclaimer: Literal["응급실 상황은 수시로 변하므로 방문 전 전화 확인을 권장합니다"]

