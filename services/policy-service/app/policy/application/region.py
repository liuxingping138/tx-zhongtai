"""信源行政区划纠正、网站编码与内部唯一 id。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

_DIGITS = re.compile(r"\D")

# 行政区划编码位数：省 2 位、市 4 位、区县 6 位，下级编码以上级编码为前缀。
PROVINCE_CODE_LENGTH = 2
CITY_CODE_LENGTH = 4
DISTRICT_CODE_LENGTH = 6


def digits_only(value: str | None) -> str:
    return _DIGITS.sub("", value or "")


def normalize_region(province_code: str, city_code: str, district_code: str) -> tuple[str, str, str]:
    """纠正并补齐：省 2 位、市 4 位、区 6 位。6 位地市编码视为误填的区县。"""

    province = digits_only(province_code)
    city = digits_only(city_code)
    district = digits_only(district_code)

    if len(city) == DISTRICT_CODE_LENGTH:
        if not district:
            district = city
        city = city[:CITY_CODE_LENGTH]

    if not province:
        source = next((code for code in (district, city) if len(code) >= PROVINCE_CODE_LENGTH), "")
        if not source:
            return "", "", ""
        province = source[:PROVINCE_CODE_LENGTH]
    province = _fit(province, PROVINCE_CODE_LENGTH)
    city = _fit(city, CITY_CODE_LENGTH) if city else _fit(province, CITY_CODE_LENGTH)
    district = _fit(district, DISTRICT_CODE_LENGTH) if district else _fit(city, DISTRICT_CODE_LENGTH)

    return district[:PROVINCE_CODE_LENGTH], district[:CITY_CODE_LENGTH], district


def _fit(code: str, length: int) -> str:
    """右补 0 或截断到固定位数。"""

    return code.ljust(length, "0")[:length]


def make_internal_id(site_name: str, province_name: str, city_name: str, tag: str) -> str:
    raw = f"{site_name}{province_name}{city_name}{tag}"
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def make_policy_uid(policy_title: str) -> str:
    return hashlib.md5((policy_title or "").encode("utf-8"), usedforsecurity=False).hexdigest()


def make_relation_key(policy_uid: str, industry_scenario_code: str, opportunity_type: str) -> str:
    return f"{policy_uid}{industry_scenario_code}{opportunity_type}"


def site_code_prefix(province_code: str, city_code: str, district_code: str) -> str:
    """网站编码前缀：有区县用 6 位区县，否则地市+00，再否则省份+0000。"""

    district = digits_only(district_code)
    city = digits_only(city_code)
    province = digits_only(province_code)
    if len(district) >= DISTRICT_CODE_LENGTH:
        return district[:DISTRICT_CODE_LENGTH]
    if len(city) >= CITY_CODE_LENGTH:
        return _fit(city[:CITY_CODE_LENGTH], DISTRICT_CODE_LENGTH)
    if len(province) >= PROVINCE_CODE_LENGTH:
        return _fit(province[:PROVINCE_CODE_LENGTH], DISTRICT_CODE_LENGTH)
    return ""


def next_site_code(district_code: str, existing_codes: Iterable[str]) -> str:
    """同区县取当前网站编码最大序号再 +1。"""

    prefix = _fit(digits_only(district_code), DISTRICT_CODE_LENGTH)
    max_seq = 0
    for code in existing_codes:
        digits = digits_only(code)
        if not digits.startswith(prefix) or len(digits) <= len(prefix):
            continue
        try:
            max_seq = max(max_seq, int(digits[len(prefix) :]))
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:05d}"
