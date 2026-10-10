from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

_SUFFIXES = (
    "特别行政区",
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "自治区",
    "自治州",
    "地区",
    "盟",
    "省",
    "市",
    "区",
    "县",
    "旗",
)


@dataclass(frozen=True)
class AreaSnap:
    prov_id: str
    prov_name: str
    city_id: str
    city_name: str
    county_id: str
    county_name: str
    alias_prov_name: str = ""
    alias_city_name: str = ""
    alias_county_name: str = ""
    city_name_short: str = ""
    county_name_short: str = ""


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    level: int
    province_code: str = ""
    city_code: str = ""
    district_code: str = ""
    reason: str = ""


def fold(name: str) -> str:
    return (name or "").replace("\u3000", "").replace(" ", "").strip()


def strip_suffix(name: str) -> str:
    text = fold(name)
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def name_variants(*names: str) -> set[str]:
    values: set[str] = set()
    for name in names:
        text = fold(name)
        if not text:
            continue
        values.add(text)
        stripped = strip_suffix(text)
        if stripped:
            values.add(stripped)
    return values


def name_hit(input_name: str, *officials: str) -> bool:
    left = name_variants(input_name)
    right = name_variants(*officials)
    return bool(left and left & right)


def _unique(rows: Iterable[AreaSnap], key: Callable[[AreaSnap], tuple[str, ...]]) -> list[AreaSnap]:
    seen: dict[tuple[str, ...], AreaSnap] = {}
    for row in rows:
        seen[key(row)] = row
    return list(seen.values())


def _fail(reason: str) -> MatchResult:
    return MatchResult(ok=False, level=0, reason=reason)


@dataclass(frozen=True)
class AreaIndex:
    county: dict[str, list[AreaSnap]]
    city: dict[str, list[AreaSnap]]
    province: dict[str, list[AreaSnap]]


def build_area_index(catalog: list[AreaSnap]) -> AreaIndex:
    county: dict[str, list[AreaSnap]] = defaultdict(list)
    city: dict[str, list[AreaSnap]] = defaultdict(list)
    province: dict[str, list[AreaSnap]] = defaultdict(list)
    for row in catalog:
        for key in name_variants(row.county_name, row.alias_county_name, row.county_name_short):
            county[key].append(row)
        for key in name_variants(row.city_name, row.alias_city_name, row.city_name_short):
            city[key].append(row)
        for key in name_variants(row.prov_name, row.alias_prov_name):
            province[key].append(row)
    return AreaIndex(county=dict(county), city=dict(city), province=dict(province))


def _lookup(index: dict[str, list[AreaSnap]], name: str) -> list[AreaSnap]:
    seen: set[int] = set()
    hits: list[AreaSnap] = []
    for key in name_variants(name):
        for row in index.get(key, ()):
            ident = id(row)
            if ident in seen:
                continue
            seen.add(ident)
            hits.append(row)
    return hits


def _in_province(rows: list[AreaSnap], province: str) -> list[AreaSnap]:
    if not province:
        return rows
    return [row for row in rows if name_hit(province, row.prov_name, row.alias_prov_name)]


def _in_city(rows: list[AreaSnap], city: str) -> list[AreaSnap]:
    if not city:
        return rows
    return [row for row in rows if name_hit(city, row.city_name, row.alias_city_name, row.city_name_short)]


def _county_candidates(index: AreaIndex, province: str, city: str, county: str) -> list[AreaSnap]:
    hits = _in_city(_in_province(_lookup(index.county, county), province), city)
    return _unique(hits, lambda row: (row.county_id,))


def _city_candidates(index: AreaIndex, province: str, city: str) -> list[AreaSnap]:
    hits = _in_province(_lookup(index.city, city), province)
    return _unique(hits, lambda row: (row.prov_id, row.city_id))


def _province_candidates(index: AreaIndex, province: str) -> list[AreaSnap]:
    return _unique(_lookup(index.province, province), lambda row: (row.prov_id,))


def match_area_indexed(index: AreaIndex, province: str, city: str, county: str) -> MatchResult:
    """能齐三级就配三级，否则二级，再否则省份。省/市/区任一配上编码即算已关联。"""

    province = fold(province)
    city = fold(city)
    county = fold(county)
    if not province and not city and not county:
        return _fail("缺少省市区名称")
    marks: list[str] = []

    if county:
        uniq = _county_candidates(index, province, city, county)
        if len(uniq) == 1:
            row = uniq[0]
            return MatchResult(True, 3, row.prov_id, row.city_id, row.county_id)
        marks.append("区县不标准" if not uniq else "区县不唯一，请补全省市名称")

    if city:
        uniq = _city_candidates(index, province, city)
        if len(uniq) == 1:
            row = uniq[0]
            return MatchResult(True, 2, row.prov_id, row.city_id, "", "；".join(marks))
        marks.append("地市不标准" if not uniq else "地市不唯一，请补全省份")

    if province:
        uniq = _province_candidates(index, province)
        if len(uniq) == 1:
            row = uniq[0]
            return MatchResult(True, 1, row.prov_id, "", "", "；".join(marks))
        marks.append("省份不标准" if not uniq else "省份不唯一")

    return _fail("；".join(marks) if marks else "未关联到省市区编码")


def match_area(catalog: list[AreaSnap], province: str, city: str, county: str) -> MatchResult:
    return match_area_indexed(build_area_index(catalog), province, city, county)
