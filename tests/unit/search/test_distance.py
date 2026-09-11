import math

import pytest

from er_finder.search.distance import distance_km


def test_distance_between_identical_points_is_zero():
    assert distance_km(37.5665, 126.9780, 37.5665, 126.9780) == 0.0


def test_distance_matches_known_reference_value():
    # One degree of longitude at the equator is ~111.195 km for this mean
    # earth radius (6371.0088 km), independent of the implementation itself.
    assert distance_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.001)


def test_distance_is_symmetric():
    a = (37.4979, 127.0276)  # 강남역
    b = (37.5563, 126.9723)  # 서울역
    assert distance_km(*a, *b) == pytest.approx(distance_km(*b, *a))


@pytest.mark.parametrize(
    "lat1, lon1, lat2, lon2",
    [
        (91, 0, 0, 0),
        (-91, 0, 0, 0),
        (0, 181, 0, 0),
        (0, -181, 0, 0),
        (math.nan, 0, 0, 0),
        (0, math.inf, 0, 0),
    ],
)
def test_distance_rejects_out_of_range_or_non_finite_coordinates(lat1, lon1, lat2, lon2):
    with pytest.raises(ValueError):
        distance_km(lat1, lon1, lat2, lon2)
