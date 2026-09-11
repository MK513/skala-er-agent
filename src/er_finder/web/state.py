"""Only input events mutate session state; rendering must never call the backend."""

import re
from dataclasses import dataclass, field

from er_finder.memory.store import ConsentRequiredError
from er_finder.web.contracts import Backend, Message, WebResult
from er_finder.web.preview import CASES, PreviewBackend


def _display_text(text: str) -> str:
    """Limited display redaction for common Korean IDs/phones, not a safety classifier."""
    text = re.sub(r"(?<!\d)\d{6}[\s-]?[1-8]\d{6}(?!\d)", "[주민번호 가림]", text)
    return re.sub(r"(?<!\d)0\d{1,2}[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)", "[전화번호 가림]", text)


@dataclass
class WebSession:
    backend: Backend = field(default_factory=PreviewBackend)
    messages: list[Message] = field(default_factory=list)
    result: WebResult | None = None
    scenario: str = "candidates"
    transport: str = "car"
    _last_query: str | None = field(default=None, repr=False)

    def _receive(self, result: WebResult) -> None:
        self.result = result
        if result.pending_approval:
            text = "방문 계획을 저장할까요? 승인 전에는 저장되지 않습니다."
        elif result.reply:
            text = result.reply.next_action
        else:
            text = result.note or "결과를 확인할 수 없습니다."
        self.messages.append(Message("assistant", text))

    def submit(self, text: str) -> None:
        text = _display_text(text.strip())
        if not text:
            return
        self.messages.append(Message("user", text))
        try:
            result = self.backend.chat(text, transport=self.transport)
        except Exception:
            self.backend.reset()
            result = WebResult(note="서비스를 실행하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        if result.pending_approval is None:
            self._last_query = text
        self._receive(result)

    def select_hospital(self, hpid: str) -> None:
        self._receive(self.backend.select_hospital(hpid))

    def decide(self, approved: bool) -> None:
        if self.result is None or self.result.pending_approval is None:
            return
        try:
            result = self.backend.approve(approved)
        except Exception:
            self.backend.reset()
            result = WebResult(
                note="저장 결과를 확인하지 못했습니다. 중복 방지를 위해 자동 재시도하지 않습니다."
            )
        self._receive(result)

    def reset(self) -> None:
        self.backend.reset()
        self.messages.clear()
        self.result = None
        self._last_query = None

    def forget(self) -> None:
        self.backend.forget()
        self.messages.clear()
        self.result = None
        self._last_query = None

    def refresh(self) -> None:
        if not self._last_query:
            return
        try:
            result = self.backend.chat(
                self._last_query, transport=self.transport, force_refresh=True
            )
        except Exception:
            self.backend.reset()
            result = WebResult(note="새로 조회하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        self._receive(result)

    def set_scenario(self, scenario: str) -> None:
        if scenario not in CASES:
            raise ValueError("알 수 없는 시연 시나리오입니다")
        if scenario != self.scenario:
            self.reset()
            self.scenario = scenario
            if isinstance(self.backend, PreviewBackend):
                self.backend.scenario = scenario

    def set_transport(self, transport: str) -> None:
        if transport not in {"car", "walk", "transit"}:
            raise ValueError("이동수단을 확인해 주세요")
        if transport != self.transport:
            self.reset()
            self.transport = transport

    def _notice(self, note: str) -> None:
        # Preserve any pending approval while changing the independent address preference.
        if self.result is None:
            self.result = WebResult(note=note)
        else:
            self.result.note = note

    def set_home_address(self, address: str, *, consent: bool) -> None:
        try:
            self.backend.profile.set_home_address(_display_text(address.strip()), consent=consent)
        except ConsentRequiredError:
            self._notice("기본 주소 저장에는 명시적인 동의가 필요합니다.")
        except ValueError:
            self._notice("저장할 주소를 입력해 주세요.")
        else:
            self._notice("동의한 기본 주소를 이 브라우저 세션에 저장했습니다.")

    def clear_home_address(self) -> None:
        self.backend.profile.clear_home_address()
        self._notice("기본 주소를 삭제했습니다.")
