"""Fixed provider responses for SearchSession tests; never used by the application."""

LOCATIONS = {
    "gangnam": (37.5, 127.0, "서울특별시", "강남구"),
    "gangneung": (37.795, 128.907, "강원특별자치도", "강릉시"),
    "yeongwol": (37.1837, 128.4614, "강원특별자치도", "영월군"),
}
# Identifier, region, latitude offset, available beds, myocardial-infarction acceptance.
ROWS = (
    ("TEST-GN-1", "gangnam", 0.005, 3, True),
    ("TEST-GN-2", "gangnam", 0.008, 2, True),
    ("TEST-GN-3", "gangnam", 0.010, 0, True),
    ("TEST-GN-4", "gangnam", 0.012, 4, False),
    ("TEST-GN-5", "gangnam", 0.020, 1, True),
    ("TEST-GL-1", "gangneung", 0.006, 2, None),
    ("TEST-YW-1", "yeongwol", 0.006, 0, None),
)


class OfflineSearchProvider:
    def geocode(self, query):
        for words, region in (
            (("강남", "역삼"), "gangnam"),
            (("강릉", "경포대"), "gangneung"),
            (("영월", "상동읍"), "yeongwol"),
        ):
            if any(word in query for word in words):
                lat, lon, sido, sigungu = LOCATIONS[region]
                return dict(found=True, lat=lat, lon=lon, sido=sido, sigungu=sigungu)
        return {"found": False}

    def list_nearby_ers(self, lat, lon, radius_km):
        # Return all fixture rows so the session must enforce the requested radius itself.
        result = []
        for hpid, region, offset, _, _ in ROWS:
            base_lat, base_lon, sido, sigungu = LOCATIONS[region]
            result.append(
                dict(
                    hpid=hpid,
                    name=f"테스트 응급센터 {hpid}",
                    lat=base_lat + offset,
                    lon=base_lon,
                    sido=sido,
                    sigungu=sigungu,
                    address=f"{sido} {sigungu} 테스트 주소",
                    er_tel=None,
                )
            )
        return result

    def get_er_bed_status(self, sido, sigungu, hpids, *, force_refresh=False):
        return [
            dict(
                hpid=hpid,
                er_beds_available=beds,
                beds_updated_at="2026-09-10T09:00:00+09:00",
                is_cached=False,
            )
            for hpid, region, _, beds, _ in ROWS
            if hpid in hpids and LOCATIONS[region][2:] == (sido, sigungu)
        ]

    def get_severe_acceptance(self, sido, sigungu, condition):
        return [
            dict(hpid=hpid, acceptable=accepted if condition == "심근경색" else None)
            for hpid, region, _, _, accepted in ROWS
            if LOCATIONS[region][2:] == (sido, sigungu)
        ]

    def get_er_detail(self, hpid):
        return {"er_tel": None}
