from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.structured_output import ToolStrategy

from er_finder.agent.prompts import SYSTEM_PROMPT
from er_finder.agent.tools import TOOLS
from er_finder.guardrails.middleware import (
    EmergencyInputGuard,
    EvidenceCheckMiddleware,
    ProfileDynamicPrompt,
)
from er_finder.guardrails.pii import PII_PATTERN
from er_finder.memory.context import RuntimeContext
from er_finder.memory.state import ERGraphState
from er_finder.models import ERSearchReply


def build_graph(model, *, checkpointer, store, session, profiles, visit):
    """도구+미들웨어를 조립해 LangGraph 에이전트 그래프를 반환한다. (미들웨어 순서=실행 훅 순서, 재배열 금지)"""
    return create_agent(
        model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(ERSearchReply, handle_errors=True),
        state_schema=ERGraphState,
        context_schema=RuntimeContext,
        checkpointer=checkpointer,
        store=store,
        middleware=[
            EmergencyInputGuard(session),  # before_agent
            ProfileDynamicPrompt(session, profiles, visit),  # before_model
            PIIMiddleware("korean_personal_data", strategy="redact", detector=PII_PATTERN),  # before_model
            ModelCallLimitMiddleware(run_limit=10, exit_behavior="end"),  # wrap_model_call
            ToolRetryMiddleware(max_retries=2, initial_delay=1.0),  # wrap_tool_call
            HumanInTheLoopMiddleware(
                interrupt_on={"save_visit_plan": {"allowed_decisions": ["approve", "reject"]}},
                description_prefix="이 방문 계획을 저장할까요?",
            ),  # after_model
            EvidenceCheckMiddleware(session),  # after_agent
        ],
    )
