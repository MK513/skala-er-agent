import re


def radius_sequence(transport: str, text: str = "") -> list[int]:
    if transport not in {"car", "walk", "transit"}:
        raise ValueError("transport must be car, walk or transit")
    radii = [3 if transport == "walk" else 5, 10, 20, 30]
    match = re.search(r"(?:반경\s*)?(3|5|10|20|30)\s*(?:km|킬로(?:미터)?)", text, re.I)
    if match:
        requested = int(match[1])
        # Explicit supported radii are respected; subsequent expansions remain bounded.
        return [requested] + [r for r in (10, 20, 30) if r > requested]
    return radii
