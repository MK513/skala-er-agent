"""Explicit latitude/longitude input, independent of address search services."""

import re

_PAIR = re.compile(r"(?<![\w.])([+-]?\d{1,3}\.\d+)\s*,\s*([+-]?\d{1,3}\.\d+)(?![\w.])")


def parse_coordinates(query: str) -> tuple[float, float] | None:
    match = _PAIR.fullmatch(query.strip())
    if match is None:
        return None
    lat, lon = map(float, match.groups())
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("위도는 -90~90, 경도는 -180~180 범위로 입력하세요.")
    return lat, lon


def extract_coordinates(text: str) -> str | None:
    match = _PAIR.search(text)
    if match is None:
        return None
    query = f"{match[1]}, {match[2]}"
    parse_coordinates(query)
    return query
