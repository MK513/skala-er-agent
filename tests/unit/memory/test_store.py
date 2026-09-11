from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from er_finder.memory.store import ConsentRequiredError, ERFinderStore


@pytest.fixture
def raw_store():
    return InMemoryStore()


@pytest.fixture
def store(raw_store):
    return ERFinderStore(raw_store, user_id="u123")


# ---------- home_address ----------


def test_get_home_address_returns_none_when_not_set(store):
    assert store.get_home_address() is None


def test_set_home_address_without_consent_raises_and_does_not_store(store):
    with pytest.raises(ConsentRequiredError):
        store.set_home_address("강남구 역삼동", consent=False)
    assert store.get_home_address() is None


def test_set_home_address_with_consent_stores_and_reads_back(store):
    store.set_home_address("강남구 역삼동", consent=True)
    assert store.get_home_address() == "강남구 역삼동"


@pytest.mark.parametrize("bad_address", ["", "   "])
def test_set_home_address_rejects_empty_address(store, bad_address):
    with pytest.raises(ValueError):
        store.set_home_address(bad_address, consent=True)


def test_clear_home_address_removes_it(store):
    store.set_home_address("강남구 역삼동", consent=True)
    store.clear_home_address()
    assert store.get_home_address() is None


def test_consent_required_error_default_message():
    err = ConsentRequiredError()
    assert "동의" in str(err)
    assert err.args[0] == err.message


# ---------- recent_visits ----------


def test_add_visit_rejects_empty_hpid_or_name(store):
    with pytest.raises(ValueError):
        store.add_visit(hpid="", name="A병원", symptom_summary="흉통")
    with pytest.raises(ValueError):
        store.add_visit(hpid="A0001", name="", symptom_summary="흉통")


def test_add_visit_returns_record_with_visit_id_and_timestamp(store):
    record = store.add_visit(hpid="A0001", name="A병원", symptom_summary="흉통")
    assert record["hpid"] == "A0001"
    assert record["name"] == "A병원"
    assert record["symptom_summary"] == "흉통"
    assert record["visit_id"]
    assert record["saved_at"]


def test_get_recent_visits_orders_newest_first_and_applies_limit(store):
    store.add_visit(hpid="A0001", name="A병원", symptom_summary="흉통")
    store.add_visit(hpid="B0002", name="B병원", symptom_summary="열상")
    store.add_visit(hpid="C0003", name="C병원", symptom_summary="복통")

    visits = store.get_recent_visits(limit=2)

    assert len(visits) == 2
    assert visits[0]["name"] == "C병원"
    assert visits[1]["name"] == "B병원"


def test_get_recent_visits_empty_when_no_visits(store):
    assert store.get_recent_visits() == []


# ---------- user 격리 ----------


def test_different_users_do_not_share_data(raw_store):
    store_a = ERFinderStore(raw_store, user_id="u123")
    store_b = ERFinderStore(raw_store, user_id="u456")

    store_a.set_home_address("강남구 역삼동", consent=True)
    store_a.add_visit(hpid="A0001", name="A병원", symptom_summary="흉통")

    assert store_b.get_home_address() is None
    assert store_b.get_recent_visits() == []
