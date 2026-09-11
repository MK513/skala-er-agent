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
    ModelCounter,
    ProfileDynamicPrompt,
    ToolSafetyMiddleware,
)
from er_finder.guardrails.pii import PII_PATTERN
from er_finder.memory.context import RuntimeContext
from er_finder.memory.state import ERGraphState
from er_finder.models import ERSearchReply


def build_graph(model, *, checkpointer, store, session, profiles, visit):
    """도구+미들웨어를 조립해 (그래프, ModelCounter)를 반환한다.

    미들웨어 순서는 실행 훅 순서이므로 재배열 금지. 단, LangChain은 같은 훅을 여러
    미들웨어가 구현할 때 wrap_tool_call/wrap_model_call은 리스트 순서(첫 항목이 최외곽)로,
    after_model은 반대로 리스트 뒤 항목이 먼저 실행되도록 그래프를 구성한다. 그래서
    HumanInTheLoopMiddleware를 ToolSafetyMiddleware보다 앞에 둬야 after_model 단계에서
    ToolSafetyMiddleware(잘못된 save_visit_plan 인자 검증/제거)가 먼저 실행되고, 그 결과를
    본 뒤에야 HumanInTheLoopMiddleware가 승인 인터럽트 여부를 판단한다.
    """
    counter = ModelCounter()
    graph = create_agent(
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
            counter,  # wrap_model_call
            HumanInTheLoopMiddleware(
                interrupt_on={"save_visit_plan": {"allowed_decisions": ["approve", "reject"]}},
                description_prefix="이 방문 계획을 저장할까요?",
            ),  # after_model (ToolSafetyMiddleware 다음에 실행됨 - 위 docstring 참고)
            ToolSafetyMiddleware(visit, session),  # after_model(먼저 실행), wrap_tool_call(최외곽)
            ToolRetryMiddleware(max_retries=2, initial_delay=1.0),  # wrap_tool_call(ToolSafety 안쪽)
            EvidenceCheckMiddleware(session),  # after_agent
        ],
    )
    return graph, counter
