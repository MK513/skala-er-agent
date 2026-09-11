from __future__ import annotations

from er_finder.memory.state import BED_CACHE_TTL_SECONDS, BedCacheEntry, ERFinderState


def test_default_state_is_empty():
    state = ERFinderState()
    assert state.messages == []
    assert state.current_location is None
    assert state.triage is None
    assert state.search_radius_km == 5
    assert state.candidates == []
    assert state.bed_cache == {}


# ---------- bed_cache (TTL) ----------


def test_get_cached_beds_returns_none_when_not_cached():
    state = ERFinderState()
    assert state.get_cached_beds("서울특별시", "강남구") is None


def test_set_and_get_cached_beds_hits_immediately():
    state = ERFinderState()
    beds = [{"hpid": "A0001", "name": "A병원"}]
    state.set_cached_beds("서울특별시", "강남구", beds)
    assert state.get_cached_beds("서울특별시", "강남구") == beds


def test_cached_beds_expire_after_ttl():
    state = ERFinderState()
    beds = [{"hpid": "A0001", "name": "A병원"}]
    state.set_cached_beds("서울특별시", "강남구", beds)
    entry = state.bed_cache[("서울특별시", "강남구")]
    assert state.get_cached_beds("서울특별시", "강남구") is not None

    entry.fetched_at -= BED_CACHE_TTL_SECONDS + 1
    assert state.get_cached_beds("서울특별시", "강남구") is None


def test_bed_cache_entry_is_expired_boundary():
    entry = BedCacheEntry(beds=[], fetched_at=100.0)
    assert entry.is_expired(now=100.0 + BED_CACHE_TTL_SECONDS) is False
    assert entry.is_expired(now=100.0 + BED_CACHE_TTL_SECONDS + 1) is True


def test_different_region_keys_do_not_share_cache():
    state = ERFinderState()
    state.set_cached_beds("서울특별시", "강남구", [{"hpid": "A0001"}])
    assert state.get_cached_beds("서울특별시", "서초구") is None


# ---------- expand_radius ----------


def test_expand_radius_moves_through_sequence_and_stops_at_end():
    state = ERFinderState()
    sequence = [5, 10, 20, 30]

    assert state.expand_radius(sequence) is True
    assert state.search_radius_km == 10
    assert state.expand_radius(sequence) is True
    assert state.search_radius_km == 20
    assert state.expand_radius(sequence) is True
    assert state.search_radius_km == 30
    assert state.expand_radius(sequence) is False
    assert state.search_radius_km == 30


def test_expand_radius_never_shrinks_when_current_value_not_in_sequence():
    # 기본값 5가 남은 상태에서 walk 시퀀스([3,10,20,30])를 적용해도
    # 3으로 되돌아가지 않고 5보다 큰 다음 값(10)으로 가야 한다.
    state = ERFinderState()
    walk_sequence = [3, 10, 20, 30]

    assert state.expand_radius(walk_sequence) is True
    assert state.search_radius_km == 10


def test_expand_radius_returns_false_when_no_larger_value_exists():
    state = ERFinderState()
    state.search_radius_km = 30
    assert state.expand_radius([5, 10, 20, 30]) is False
    assert state.search_radius_km == 30


# ---------- reset_location_scoped ----------


def test_reset_location_scoped_clears_radius_candidates_and_cache():
    state = ERFinderState()
    state.search_radius_km = 20
    state.candidates = [{"hpid": "A0001"}]
    state.set_cached_beds("서울특별시", "강남구", [{"hpid": "A0001"}])

    state.reset_location_scoped()

    assert state.search_radius_km == 5
    assert state.candidates == []
    assert state.bed_cache == {}


def test_reset_location_scoped_honors_initial_radius_km_for_transport():
    state = ERFinderState()
    state.search_radius_km = 20

    state.reset_location_scoped(initial_radius_km=3)

    assert state.search_radius_km == 3
