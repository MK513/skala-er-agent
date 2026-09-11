"""Compatibility imports; implementations live in guardrails/."""

from er_finder.guardrails.evidence import safe_data, sanitize_prose
from er_finder.guardrails.input_guard import assess_input
from er_finder.guardrails.pii import PII_PATTERN, mask_pii, normalize

__all__ = ["assess_input", "mask_pii", "normalize", "PII_PATTERN", "safe_data", "sanitize_prose"]
