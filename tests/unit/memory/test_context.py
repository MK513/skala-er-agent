from __future__ import annotations

import dataclasses

import pytest

from er_finder.memory.context import ERFinderContext


def test_default_transport_is_car():
    ctx = ERFinderContext(user_id="u123")
    assert ctx.user_id == "u123"
    assert ctx.transport == "car"


@pytest.mark.parametrize("transport", ["walk", "car", "transit"])
def test_accepts_all_valid_transport_modes(transport):
    ctx = ERFinderContext(user_id="u123", transport=transport)
    assert ctx.transport == transport


def test_is_frozen_and_rejects_reassignment():
    ctx = ERFinderContext(user_id="u123")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_id = "other"
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.transport = "walk"


@pytest.mark.parametrize("bad_user_id", ["", "   "])
def test_rejects_empty_or_blank_user_id(bad_user_id):
    with pytest.raises(ValueError):
        ERFinderContext(user_id=bad_user_id)


def test_rejects_transport_outside_literal_values_at_runtime():
    # Literal은 타입체커만 검사하므로 런타임 검증이 따로 필요하다.
    with pytest.raises(ValueError):
        ERFinderContext(user_id="u123", transport="bike")
