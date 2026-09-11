from langchain.tools import tool
from langchain_core.runnables import RunnableConfig

from er_finder.memory.visit_plan import PendingVisitPlan, VisitPlanService

@tool
def geocode(query: str, config: RunnableConfig) -> dict:
    """사용자의 주소·동·건물·역을 좌표로 변환한다. 응급실 목록 전에 호출한다."""
    session = config["configurable"]["session"]
    return session.geocode(query)

@tool
def list_nearby_ers(lat: float, lon: float, radius_km: int, config: RunnableConfig) -> list[dict]:
    """확인된 좌표와 허용된 다음 반경으로 응급실 목록을 조회한다. 반경은 30km 이하."""
    session = config["configurable"]["session"]
    return session.list_nearby_ers(lat, lon, radius_km)

@tool
def get_er_bed_status(sido: str, sigungu: str, hpids: list[str], config: RunnableConfig) -> list[dict]:
    """목록의 시도·시군구 조합별 병상을 조회·병합하고 목록의 hpid만 반환한다."""
    session = config["configurable"]["session"]
    return session.get_er_bed_status(sido, sigungu, hpids)

@tool
def get_severe_acceptance(sido: str, sigungu: str, condition: str, config: RunnableConfig) -> list[dict]:
    """critical/urgent의 조회 조건이 있을 때 시군구별 중증 수용 정보를 조회한다."""
    session = config["configurable"]["session"]
    return session.get_severe_acceptance(sido, sigungu, condition)

@tool
def get_er_detail(hpid: str, config: RunnableConfig) -> dict:
    """병상·수용 조건을 통과한 상위 3곳의 직통 전화·주소·시간을 항상 조회한다. 병렬 가능."""
    session = config["configurable"]["session"]
    return session.get_er_detail(hpid);

@tool
def save_visit_plan(hpid: str, name: str, symptom_summary: str, config: RunnableConfig) -> dict:
    """사용자가 선택한 병원과 증상 요약을 명시적 HITL 승인 이후에만 저장한다."""
    # HumanInTheLoopMiddleware가 이 도구 호출 자체를 승인 이후에만 실행하므로,
    # 여기 도달했다는 것 자체가 승인됨을 의미한다(interfaces.md §2 도구 규약).
    profile_store = config["configurable"]["profile_store"]
    plan = PendingVisitPlan(hpid=hpid, name=name, symptom_summary=symptom_summary)
    result = VisitPlanService(profile_store).decide(plan, approved=True)
    return result.as_dict()

TOOLS = [geocode, list_nearby_ers, get_er_bed_status, get_severe_acceptance, get_er_detail, save_visit_plan]