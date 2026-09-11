"""agent 폴더 테스트용 픽스처.

runner.py 자체의 로직(문자열 처리, 분기, 상태 전이, 예외 처리)을 검증할 수 있도록, 이 conftest는
필요한 이름만 채운 최소 스텁 모듈을 sys.modules에 등록한 뒤 runner.py를 새로 import한다.
스텁은 테스트가 끝나면 정리되므로 다른 테스트 파일(import 경로가 이미 존재하는
er_finder.agent.tools 등)에는 영향을 주지 않는다.

실제 LLM 모델 호출은 어디에서도 발생하지 않는다: create_agent 자체를 MagicMock으로
대체해 만든 가짜 그래프의 invoke()만 호출한다.
"""

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from er_finder.models import ERSearchReply, HospitalCandidate

_STUB_MODULE_NAMES = [
    "er_finder.cli.renderer",
    "er_finder.guardrails.middleware",
    "er_finder.guardrails.pii",
    "er_finder.guardrails.triage",
    "er_finder.memory.context",
    "er_finder.memory.session",
    "er_finder.memory.state",
    "er_finder.memory.store",
    "er_finder.memory.visit_plan",
    "er_finder.safety",
    "er_finder.search.service",
]


class _StubSearchSession:
    def __init__(self, provider, transport):
        self.provider = provider
        self.transport = transport
        self.now = MagicMock(return_value="now")
        self.symptom_text = None
        self.assessment = MagicMock(reason=None)
        self.begin = MagicMock()
        self.make_reply = MagicMock()
        self.check_evidence = MagicMock()
        self.geocode = MagicMock()
        self.list_nearby_ers = MagicMock()
        self.get_er_bed_status = MagicMock()
        self.get_severe_acceptance = MagicMock()
        self.get_er_detail = MagicMock()
        self.save_visit_plan = MagicMock()


class _StubProfiles:
    def __init__(self, user_id, store):
        self.user_id = user_id
        self.store = store
        self.home_address = MagicMock(return_value=None)
        self.recent_visits = MagicMock(return_value=[])


class _StubVisitPlan:
    def __init__(self, profiles, now):
        self.profiles = profiles
        self.now = now
        self.prepare = MagicMock()
        self.reset = MagicMock()
        self.pending = {}
        self.approved = None
        self.decided = None


class _StubRuntimeContext:
    def __init__(self, user_id, transport):
        self.user_id = user_id
        self.transport = transport


class _StubInputClassifier:
    def assess(self, text):  # pragma: no cover - 테스트는 항상 자체 mock classifier를 주입한다
        raise NotImplementedError("테스트에서 classifier를 직접 주입하세요.")


def _register_stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


@pytest.fixture
def runner_module(monkeypatch):
    """스텁을 심고 er_finder.agent.runner를 새로 import해서 돌려준다."""
    import er_finder.models as models_module

    monkeypatch.setattr(models_module, "EMERGENCY", "EMERGENCY_SENTINEL", raising=False)

    _register_stub_module("er_finder.cli.renderer", render_reply=lambda reply, note=None, pending=None: "rendered")
    _register_stub_module(
        "er_finder.guardrails.middleware",
        EmergencyInputGuard=lambda *a, **k: MagicMock(name="EmergencyInputGuard"),
        EvidenceCheckMiddleware=lambda *a, **k: MagicMock(name="EvidenceCheckMiddleware"),
        ProfileDynamicPrompt=lambda *a, **k: MagicMock(name="ProfileDynamicPrompt"),
    )
    _register_stub_module("er_finder.guardrails.pii", PII_PATTERN=object())
    _register_stub_module("er_finder.guardrails.triage", InputClassifier=_StubInputClassifier)
    _register_stub_module("er_finder.memory.context", RuntimeContext=_StubRuntimeContext)
    _register_stub_module(
        "er_finder.memory.session",
        clear_session=MagicMock(),
        make_checkpointer=MagicMock(return_value=MagicMock(name="checkpointer")),
    )
    _register_stub_module("er_finder.memory.state", ERGraphState=object)
    _register_stub_module("er_finder.memory.store", Profiles=_StubProfiles)
    _register_stub_module(
        "er_finder.memory.visit_plan",
        VisitPlan=_StubVisitPlan,
        selected_index=lambda text: None,
    )
    _register_stub_module("er_finder.safety", mask_pii=lambda text: text, safe_data=lambda value: value)
    _register_stub_module("er_finder.search.service", SearchSession=_StubSearchSession)

    sys.modules.pop("er_finder.agent.runner", None)
    module = importlib.import_module("er_finder.agent.runner")

    yield module

    sys.modules.pop("er_finder.agent.runner", None)
    for name in _STUB_MODULE_NAMES:
        sys.modules.pop(name, None)


@pytest.fixture
def make_finder(runner_module):
    def _make(**overrides):
        kwargs = dict(
            provider=MagicMock(name="provider"),
            model="fake-model",
            classifier=MagicMock(name="classifier"),
            user_id="u1",
            transport="car",
            store=None,
            checkpointer=MagicMock(name="checkpointer"),
            on_emergency=None,
        )
        kwargs.update(overrides)

        fake_graph = MagicMock(name="graph")
        fake_graph.invoke.return_value = {"structured_response": None}
        runner_module.create_agent = MagicMock(return_value=fake_graph)

        return runner_module.ERFinder(**kwargs)

    return _make


@pytest.fixture
def make_reply():
    def _make(**overrides):
        data = dict(
            severity="standard",
            call_119_first=False,
            search_radius_km=5,
            hospitals=[],
            no_candidate_reason="후보를 찾지 못했습니다",
            data_timestamp="2026-01-01T00:00:00+09:00",
            next_action="가까운 병원에 전화로 확인하세요",
            disclaimer="응급실 상황은 수시로 변하므로 방문 전 전화 확인을 권장합니다",
        )
        data.update(overrides)
        return ERSearchReply(**data)

    return _make


@pytest.fixture
def make_hospital():
    def _make(**overrides):
        data = dict(
            hpid="H1",
            name="서울병원",
            distance_km=1.2,
            er_beds_available=2,
            beds_updated_at="2026-01-01T00:00:00+09:00",
            accepts_condition="unknown",
            er_tel="02-000-0000",
            address="서울시 어딘가",
            is_cached=False,
            is_stale=False,
        )
        data.update(overrides)
        return HospitalCandidate(**data)

    return _make


@pytest.fixture
def make_assessment():
    def _make(severity="standard", blocked=False):
        return SimpleNamespace(triage=SimpleNamespace(severity=severity), blocked=blocked)

    return _make
